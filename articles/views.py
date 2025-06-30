#articles/views.py
from rest_framework import viewsets
from .models import PlagiarismCheck
from .serializers import ReportSerializer, PlagiarismCheckSerializer
from django.views.generic import TemplateView, DetailView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import DeleteView
from django.urls import reverse_lazy
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ReportForm
from django.contrib.auth.mixins import LoginRequiredMixin
import io
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings
import os
from .external_search import search_google_fragment
from .ai_detection import detect_ai
from .models import Report

def analyze_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    text = report.content.strip()
    if not text:
        messages.error(request, "Текст доклада пустой.")
        return redirect('get_reference', report_id=report.id)

    # Разбиваем текст на фрагменты по 25 слов с шагом 20
    words = text.split()
    fragment_size = 25
    step = 20
    fragments = [
        " ".join(words[i:i + fragment_size])
        for i in range(0, len(words), step)
        if len(words[i:i + fragment_size]) >= 10
    ]

    plagiarism_hits = 0
    total_checked = 0

    for frag in fragments:
        try:
            results = search_google_fragment(frag)
            if results:  # Найдены внешние совпадения
                plagiarism_hits += 1
            total_checked += 1
        except Exception as e:
            print(f"[Ошибка поиска] {e}")
            continue

    if total_checked == 0:
        originality_percent = 100.0
    else:
        originality_percent = max(0, 100 - (plagiarism_hits / total_checked) * 100)

    # Проверка на AI
    try:
        ai_score = detect_ai(text)
        ai_score = float(ai_score) if ai_score is not None else 0.0
        print(f"[AI detection] AI score: {ai_score}")
    except Exception as e:
        print(f"[Ошибка AI-анализа] {e}")
        ai_score = 0.0

    # Сохраняем результаты
    report.originality_percent = round(originality_percent, 2)
    report.ai_generated_percent = round(ai_score, 2)
    report.save()

    messages.success(request, f"Проверка завершена. Оригинальность: {originality_percent:.2f}%, ИИ: {ai_score:.2f}%")
    return redirect('get_reference', report_id=report.id)

class ReportViewSet(viewsets.ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer


class PlagiarismCheckViewSet(viewsets.ModelViewSet):
    queryset = PlagiarismCheck.objects.all()
    serializer_class = PlagiarismCheckSerializer


class RegisterReportPageView(LoginRequiredMixin, View):
    template_name = 'register_report.html'

    def get(self, request):
        reports = Report.objects.filter(author=request.user).order_by('-created_at')
        form = ReportForm()
        return render(request, self.template_name, {'reports': reports, 'form': form})

    def post(self, request):
        form = ReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.author = request.user
            report.save()
            messages.success(request, 'Доклад успешно зарегистрирован!')
            return redirect('register_report')
        messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        reports = Report.objects.filter(author=request.user).order_by('-created_at')
        return render(request, self.template_name, {'reports': reports, 'form': form})


class ReportDetailView(DetailView):
    model = Report
    template_name = 'info_report.html'  # <-- шаблон конкретного доклада
    context_object_name = 'report'


class GetReferenceListView(LoginRequiredMixin, TemplateView):
    template_name = 'report.html'  # <-- список всех докладов пользователя

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            context['reports'] = Report.objects.filter(author=user).order_by('-created_at')
        else:
            context['reports'] = []
        return context

class GetReferenceView(TemplateView):
    template_name = 'get-reference.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report_id = self.kwargs.get('report_id')
        report = get_object_or_404(Report, id=report_id)
        context['report'] = report
        return context

class EditReportView(LoginRequiredMixin, View):
    template_name = 'edit_report.html'

    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk, author=request.user)
        form = ReportForm(instance=report)
        return render(request, self.template_name, {'form': form, 'report': report})

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk, author=request.user)
        form = ReportForm(request.POST, request.FILES, instance=report)
        if form.is_valid():
            form.save()
            messages.success(request, 'Доклад успешно обновлён!')
            return redirect('report_info', pk=report.pk)
        messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        return render(request, self.template_name, {'form': form, 'report': report})

class ReportDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Report
    template_name = 'reports/report_confirm_delete.html'  # можно использовать стандартный, или не создавать, т.к. форма не используется
    success_url = reverse_lazy('profile')

    def test_func(self):
        report = self.get_object()
        return report.author == self.request.user

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Доклад успешно удалён.")
        return super().delete(request, *args, **kwargs)


def generate_certificate(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)

    # Подключаем кириллический шрифт из папки static
    font_path = os.path.join(settings.BASE_DIR, 'static', 'DejaVuSans.ttf')
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    p.setFont("DejaVu", 14)

    p.drawString(100, 800, "Справка по докладу")
    p.drawString(100, 760, f"Название: {report.title}")
    p.drawString(100, 740, f"Автор: {report.author.full_name} ({report.author.email})")
    p.drawString(100, 720, f"Дата: {report.created_at.strftime('%d.%m.%Y %H:%M')}")

    originality = report.originality_percent if report.originality_percent is not None else "–"
    ai_generated = report.ai_generated_percent if report.ai_generated_percent is not None else "–"

    p.drawString(100, 700, f"Оригинальность: {originality}%")
    p.drawString(100, 680, f"ИИ-генерация: {ai_generated}%")

    p.showPage()
    p.save()

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="certificate_report_{report.id}.pdf"'
    return response