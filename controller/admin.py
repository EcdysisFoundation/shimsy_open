from django.contrib import admin


from .models import ScanSettings, ScanConfiguration

admin.site.register(ScanConfiguration)
