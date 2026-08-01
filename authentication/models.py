import json
from django.contrib.auth.models import User
from django.db import models


class Collection(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('owner', 'name')

    def __str__(self):
        return self.name


class Environment(models.Model):
    """A named set of {{variables}}. Optionally scoped to one collection."""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='environments')
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name='environments',
        null=True, blank=True
    )
    name = models.CharField(max_length=80)
    variables_json = models.TextField(default='{}')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def get_vars(self):
        try:
            return json.loads(self.variables_json)
        except (ValueError, TypeError):
            return {}

    def set_vars(self, d):
        self.variables_json = json.dumps(d)

    def __str__(self):
        return self.name


class SavedRequest(models.Model):
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='requests')
    name = models.CharField(max_length=150)
    method = models.CharField(max_length=10, default='GET')
    url = models.CharField(max_length=1000)
    headers_json = models.TextField(default='[]')     # [{"key": "...", "val": "..."}]
    body = models.TextField(blank=True)
    auth_type = models.CharField(max_length=20, default='none')
    auth_data_json = models.TextField(default='{}')    # token / username+password / key+value
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']

    def get_headers(self):
        try:
            return json.loads(self.headers_json)
        except (ValueError, TypeError):
            return []

    def get_auth_data(self):
        try:
            return json.loads(self.auth_data_json)
        except (ValueError, TypeError):
            return {}

    def __str__(self):
        return f"{self.method} {self.name}"


class RequestHistory(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='history_entries')
    saved_request = models.ForeignKey(
        'SavedRequest', on_delete=models.SET_NULL, null=True, blank=True, related_name='history'
    )
    method = models.CharField(max_length=10)
    url = models.CharField(max_length=1000)
    headers_json = models.TextField(default='[]')
    body = models.TextField(blank=True)
    auth_type = models.CharField(max_length=20, default='none')
    auth_data_json = models.TextField(default='{}')
    status_code = models.IntegerField(default=0)
    status_category = models.CharField(max_length=20, default='server_error')
    elapsed_ms = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Request history'

    def get_headers(self):
        try:
            return json.loads(self.headers_json)
        except (ValueError, TypeError):
            return []

    def __str__(self):
        return f"{self.method} {self.url} -> {self.status_code}"

class Flow(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flows')
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FlowStep(models.Model):
    """One step in a flow = one saved request, executed once, that can
    extract zero or more variables from its response for later steps."""
    flow = models.ForeignKey(Flow, on_delete=models.CASCADE, related_name='steps')
    saved_request = models.ForeignKey(SavedRequest, on_delete=models.CASCADE, related_name='flow_steps')
    order = models.PositiveIntegerField(default=0)
    extractions_json = models.TextField(default='[]')  # [{"type": "json"|"html", "path": "...", "var_name": "..."}]

    class Meta:
        ordering = ['order', 'id']

    def get_extractions(self):
        try:
            return json.loads(self.extractions_json)
        except (ValueError, TypeError):
            return []

    def set_extractions(self, data):
        self.extractions_json = json.dumps(data)

    def __str__(self):
        return f"{self.flow.name} step {self.order}: {self.saved_request.name}"
class AssertionConfig(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='assertion_config')
    assertions_json = models.TextField(default='[]')

    def get_assertions(self):
        try:
            return json.loads(self.assertions_json)
        except (ValueError, TypeError):
            return []

    def set_assertions(self, data):
        self.assertions_json = json.dumps(data)