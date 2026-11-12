from django import forms
from .models import Dispute, DisputeEvidence

class DisputeForm(forms.ModelForm):
    class Meta:
        model = Dispute
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

class DisputeEvidenceForm(forms.ModelForm):
    class Meta:
        model = DisputeEvidence
        fields = ['file', 'description']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'Describe this evidence (optional)'})
        }
