# forms.py
from django import forms
from .models import Report  # или твоя модель доклада

class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'file', 'author', 'other_fields_if_any']
