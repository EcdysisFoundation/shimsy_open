from django.urls import path
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('run/', views.run_full_scan, name='run_scan'),
    path('stop/', views.stop_scan, name='stop_scan'),
    path('return-home/', views.return_home, name='return_home'),
    path("history/", views.scan_history, name="scan-history"),
    path("unstitched/", views.unstitched_runs, name="unstitched_runs"),
    path('export-csv/', views.export_csv, name='export_csv'),
    path("retake-sample/", views.retake_sample, name="retake_sample"),
    path("upload-to-stitcher/", views.upload_latest_run_to_stitcher, name="upload_to_stitcher"),
    path("get-run-subfolders/", views.get_run_subfolders_info, name="get_run_subfolders"),
    path("get-all-runs/", views.get_all_run_folders, name="get_all_runs"),
    path("get-folder-images/", views.get_folder_images, name="get_folder_images"),
    path("serve-image/", views.serve_image, name="serve_image"),
    path("check-stitching-status/", views.check_stitching_status, name="check_stitching_status"),
    path("get-folder-management-data/", views.get_folder_management_data, name="get_folder_management_data"),
    path("rename-folder/", views.rename_folder, name="rename_folder"),
    path("discard-unstitched-run/", views.discard_unstitched_run, name="discard_unstitched_run"),
    path("rotate-image/", views.rotate_image, name="rotate_image"),
    path("rescan-samples/", views.rescan_samples, name="rescan_samples"),
    path("api/rescan-request/", views.create_rescan_request, name="create_rescan_request"),
    path("api/trigger-rescan/", views.trigger_rescan_for_dish, name="trigger_rescan"),
    path("api/get-rescan-requests/", views.get_rescan_requests, name="get_rescan_requests"),
]
