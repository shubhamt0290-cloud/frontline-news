# added by shubham - form used by logged-in users to create/edit their own posts
from django import forms

from .models import News


class NewsForm(forms.ModelForm):
    class Meta:
        model = News
        fields = ('title', 'category', 'description', 'content', 'image')
        labels = {
            'description': 'Summary',
            'image': 'Image URL (optional)',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'rows': 12}),
        }
