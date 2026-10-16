from django import forms

class SearchForm(forms.Form):
    server = forms.ChoiceField(label="Server", choices=[])
    mode = forms.ChoiceField(label="Search in", choices=[("text", "File contents · ripgrep"), ("files", "Filenames · fd")], initial="text")
    query = forms.CharField(label="Search query", max_length=500, strip=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. connection refused or settings.py", "autofocus": True, "autocomplete": "off"}))
    case_sensitive = forms.BooleanField(required=False, label="Case sensitive")
    regex = forms.BooleanField(required=False, label="Regular expression")
    hidden = forms.BooleanField(required=False, label="Include hidden files")
    limit = forms.IntegerField(label="Result limit", min_value=1, max_value=500, initial=100)

    def __init__(self, *args, servers, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["server"].choices = [(s["id"], s["label"]) for s in servers]

    def clean_query(self):
        query = self.cleaned_data["query"]
        if not query.strip():
            raise forms.ValidationError("Enter search text.")
        if any(ord(c) < 32 or ord(c) == 127 for c in query):
            raise forms.ValidationError("Use a single line without control characters.")
        return query
