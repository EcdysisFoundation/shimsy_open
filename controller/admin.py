from django.contrib import admin


from .models import ScanSettings, ScanConfiguration, RescanRequest

admin.site.register(ScanConfiguration)
admin.site.register(RescanRequest)