#articles/views.py
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rest_framework import viewsets
from .models import PlagiarismCheck, Report
from .serializers import ReportSerializer, PlagiarismCheckSerializer
from django.views.generic import TemplateView, DetailView, DeleteView
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.urls import reverse_lazy
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ReportForm
import io
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings
import os
from .external_search import search_google_fragment
from .ai_detection import detect_ai

# Новый импорт для извлечения текста из PDF
import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_file):
    text = ''
    try:
        pdf_file.seek(0)  # обязательно сбрасываем указатель в начало файла
        with fitz.open(stream=pdf_file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print(f"[Ошибка чтения PDF] {e}")
        return ''
    return text.strip()


def analyze_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)

    text = report.content.strip()
    if not text:
        messages.error(request, "Текст доклада пустой.")
        return redirect('get_reference', report_id=report.id)

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
    detailed_matches = []

    for frag in fragments:
        try:
            results = search_google_fragment(frag)
            best_match = None
            best_score = 0.0

            for res in results:
                try:
                    vectorizer = TfidfVectorizer().fit_transform([frag, res["snippet"]])
                    cos_sim = cosine_similarity(vectorizer[0:1], vectorizer[1:2])[0][0]
                    sim_percent = round(cos_sim * 100, 2)
                except Exception as e:
                    print(f"[Ошибка косинусного сравнения] {e}")
                    sim_percent = 0.0

                if sim_percent > best_score:
                    best_score = sim_percent
                    best_match = {
                        "fragment": frag,
                        "similarity_percent": sim_percent,
                        "url": res["url"],
                        "title": res["title"],
                        "snippet": res["snippet"]
                    }

            if best_score >= 60.0 and best_match:
                plagiarism_hits += 1
                detailed_matches.append(best_match)

            total_checked += 1

        except Exception as e:
            print(f"[Ошибка поиска] {e}")
            continue

    originality_percent = 100.0 if total_checked == 0 else max(0.0, 100.0 - (plagiarism_hits / total_checked) * 100.0)

    try:
        ai_score = detect_ai(text)
        ai_score = float(ai_score) if ai_score is not None else 0.0
        print(f"[AI detection] AI score: {ai_score}")
    except Exception as e:
        print(f"[Ошибка AI-анализа] {e}")
        ai_score = 0.0

    report.originality_percent = round(originality_percent, 2)
    report.ai_generated_percent = round(ai_score, 2)
    report.save()

    request.session['plagiarism_details'] = detailed_matches

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

            # Автоматическое извлечение текста из PDF, если content пустой и файл загружен
            if not report.content and report.file:
                extracted_text = extract_text_from_pdf(report.file)
                if extracted_text:
                    report.content = extracted_text
                else:
                    messages.warning(request, "Не удалось извлечь текст из PDF.")

            if not report.content:
                messages.error(request, "Доклад не может быть пустым. Введите текст или загрузите PDF.")
                reports = Report.objects.filter(author=request.user).order_by('-created_at')
                return render(request, self.template_name, {'reports': reports, 'form': form})

            report.save()
            messages.success(request, 'Доклад успешно зарегистрирован!')
            return redirect('register_report')

        messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        reports = Report.objects.filter(author=request.user).order_by('-created_at')
        return render(request, self.template_name, {'reports': reports, 'form': form})


class ReportDetailView(DetailView):
    model = Report
    template_name = 'info_report.html'
    context_object_name = 'report'


class GetReferenceListView(LoginRequiredMixin, TemplateView):
    template_name = 'report.html'

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

        plagiarism_details = self.request.session.pop('plagiarism_details', None)
        context['plagiarism_details'] = plagiarism_details if plagiarism_details else []

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
            report = form.save(commit=False)

            if not report.content and report.file:
                extracted_text = extract_text_from_pdf(report.file)
                if extracted_text:
                    report.content = extracted_text
                else:
                    messages.warning(request, "Не удалось извлечь текст из PDF.")

            if not report.content:
                messages.error(request, "Доклад не может быть пустым. Введите текст или загрузите PDF.")
                return render(request, self.template_name, {'form': form, 'report': report})

            report.save()
            messages.success(request, 'Доклад успешно обновлён!')
            return redirect('report_info', pk=report.pk)

        messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        return render(request, self.template_name, {'form': form, 'report': report})


class ReportDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Report
    template_name = 'reports/report_confirm_delete.html'
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
