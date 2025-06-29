#articles/views.py
from django.views import View
from django.shortcuts import render
from rest_framework import viewsets
from .models import PlagiarismCheck
from .serializers import ReportSerializer, PlagiarismCheckSerializer
from django.views.generic import TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
import random
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

    # Разбиваем текст на фрагменты
    fragments = report.content.split('. ')
    external_hits = []

    for frag in fragments[:5]:  # Проверим только первые 5 фрагментов
        matches = search_google_fragment(frag)
        if matches:
            external_hits.append({
                "fragment": frag,
                "matches": matches
            })

    # Простейшая метрика оригинальности
    originality_score = 100 - len(external_hits) * 15
    originality_score = max(0, originality_score)

    # Определение вероятности AI
    ai_generated = detect_ai(report.content)

    # Сохраняем в модель
    report.originality_percent = originality_score
    report.ai_generated_percent = ai_generated
    report.save()

    # (Дополнительно) можно сохранить external_hits в Report как JSONField или отдельную модель

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
        return render(request, self.template_name, {'reports': reports})

    def post(self, request):
        title = request.POST.get('title')
        content = request.POST.get('text')

        if title and content:
            Report.objects.create(
                title=title,
                content=content,
                author=request.user
            )
            messages.success(request, 'Доклад успешно зарегистрирован!')
            return redirect('register_report')

        messages.error(request, 'Пожалуйста, заполните все поля.')
        reports = Report.objects.filter(author=request.user).order_by('-created_at')
        return render(request, self.template_name, {'reports': reports})


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
        return render(request, self.template_name, {'report': report})

    def post(self, request, pk):
        report = get_object_or_404(Report, pk=pk, author=request.user)
        title = request.POST.get('title')
        content = request.POST.get('content')
        file = request.FILES.get('file')

        if not title or not content:
            messages.error(request, 'Пожалуйста, заполните все обязательные поля.')
            return render(request, self.template_name, {'report': report})

        report.title = title
        report.content = content
        if file:
            report.file = file
        report.save()

        messages.success(request, 'Доклад успешно обновлён!')
        return redirect('report_info', pk=report.pk)

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