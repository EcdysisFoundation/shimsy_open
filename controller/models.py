from django.db import models


class ScanSettings(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Unique name for this scan setting")
    sample_1 = models.CharField(max_length=100)
    sample_2 = models.CharField(max_length=100)
    sample_3 = models.CharField(max_length=100)
    sample_4 = models.CharField(max_length=100)
    sample_5 = models.CharField(max_length=100)
    sample_6 = models.CharField(max_length=100)

    delay = models.FloatField(default=0.005)
    grid_rows = models.IntegerField(default=3)
    grid_cols = models.IntegerField(default=3)
    gap_x = models.IntegerField(default=2220)
    gap_y = models.IntegerField(default=3100)
    x_steps = models.IntegerField(default=505)
    y_steps = models.IntegerField(default=610)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class ScanRecord(models.Model):
    name = models.CharField(max_length=100, default="")
    name2 = models.CharField(max_length=100, default="", blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    site_number = models.CharField(max_length=4)
    sample_type = models.CharField(max_length=50)
    transect = models.CharField(max_length=10)
    run_number = models.IntegerField(default=1)
    retake = models.BooleanField(default=False)
    is_splitted = models.BooleanField(default=False, help_text="True if this sample was split (duplicate)")

    def __str__(self):
        return f"{self.site_number} - {self.sample_type} - {self.transect} at {self.timestamp}"
class ScanConfiguration(models.Model):
    delay = models.FloatField(default=0.005)
    grid_rows = models.IntegerField(default=3)
    grid_cols = models.IntegerField(default=3)
    gap_x = models.IntegerField(default=2220)
    gap_y = models.IntegerField(default=3100)
    x_steps = models.IntegerField(default=505)
    y_steps = models.IntegerField(default=610)

    def __str__(self):
        return "Current Scan Configuration"

    class Meta:
        verbose_name = "Scan Configuration"
        verbose_name_plural = "Scan Configuration"

class UnstitchedRun(models.Model):
    """Track runs that haven't been fully stitched yet"""
    run_folder = models.CharField(max_length=200, unique=True, help_text="Name of the run folder (e.g., run_001)")
    run_path = models.CharField(max_length=500, help_text="Full path to the run folder")
    total_subfolders = models.IntegerField(default=0, help_text="Total number of subfolders in this run")
    stitched_subfolders = models.IntegerField(default=0, help_text="Number of subfolders that have been successfully stitched")
    stitched_folder_names = models.TextField(default="", blank=True, help_text="JSON list of stitched folder names")
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    is_complete = models.BooleanField(default=False, help_text="True when 6 or more subfolders have been successfully stitched")
    def __str__(self):
        if self.is_complete:
            status = f"Complete ({self.stitched_subfolders} stitched)"
        else:
            status = f"{self.stitched_subfolders}/{self.total_subfolders} stitched"
        return f"{self.run_folder} - {status}"
    @property
    def stitching_progress(self):
        """Calculate stitching progress as percentage"""
        if self.total_subfolders == 0:
            return 100
        return (self.stitched_subfolders / self.total_subfolders) * 100
    def get_stitched_folders(self):
        """Get list of stitched folder names"""
        import json
        try:
            return json.loads(self.stitched_folder_names) if self.stitched_folder_names else []
        except:
            return []
    def set_stitched_folders(self, folder_names):
        """Set list of stitched folder names"""
        import json
        self.stitched_folder_names = json.dumps(folder_names)
        self.stitched_subfolders = len(folder_names)
        self.is_complete = self.stitched_subfolders >= 6
        self.save()
    class Meta:
        verbose_name = "Unstitched Run"
        verbose_name_plural = "Unstitched Runs"
        ordering = ['-created_at']