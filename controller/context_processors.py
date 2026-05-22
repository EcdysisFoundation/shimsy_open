from shimsy_secrets import get_config


def shimsy_frontend(request):
    cfg = get_config()
    form_base = (cfg.get("stitcher_form_url_base") or "").rstrip("/")
    return {
        "shimsy_stitcher_form_url_base": form_base,
    }
