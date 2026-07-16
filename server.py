from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from datetime import date
from pathlib import Path

from cleanup_service import (
    bulk_delete_by_date,
    delete_folder as delete_folder_record,
    delete_share_only,
    parse_date_field,
)
from cloud_providers.base import CloudProviderError
from cloud_providers.registry import PROVIDERS
from cloud_service import CloudService
from config import (
    BASE_DIR,
    BASE_URL,
    DEFAULT_EXPIRY_DAYS,
    FLASK_DEBUG,
    HOST,
    MAX_EXPIRY_DAYS,
    MIN_EXPIRY_DAYS,
    PORT,
    SECRET_KEY,
)
from database import DataStore
from email_compose import (
    EmailComposeError,
    compose_share_email,
    default_email_intro,
    default_sender_name,
)
from qr_generator import (
    BORDER_STYLES,
    LOGO_PLACEMENTS,
    QR_THEMES,
    QrAssetError,
    brand_image_bytes,
    build_share_url,
    default_branding_dir,
    default_qr_path,
    ensure_qr_image,
    save_png_upload,
)
from file_service import delete_folder_files
from expiry import ExpiryError, expiry_limits, format_duration, parse_expiry_form
from share_service import (
    create_share,
    format_expiry,
    format_share_expiry_message,
    format_time_remaining,
    process_expired_shares,
    revoke_share,
)
from sync_service import refresh_from_cloud
from update_check import check_for_update, clear_update_cache
from version_info import get_app_info

from oauth_bundled import is_google_oauth_bundled, seed_google_oauth_settings

store = DataStore()
seed_google_oauth_settings(store)
cloud = CloudService(store)

EXPIRED_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Link unavailable</title>
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body class="public-page">
  <div class="public-card">
    <h1>This share link is no longer available</h1>
    <p>The QR code has expired or was deactivated. Request a new link from the folder owner.</p>
  </div>
</body>
</html>
"""

NOT_FOUND_HTML = EXPIRED_HTML.replace(
    "This share link is no longer available",
    "Share link not found",
).replace(
    "The QR code has expired or was deactivated. Request a new link from the folder owner.",
    "This QR code does not match any active share link.",
)


def _cloud_context() -> dict:
    active = cloud.get_active_provider_id()
    info = cloud.provider_info(active)
    return {
        "cloud_providers": PROVIDERS,
        "active_provider": active,
        "active_provider_info": info,
        "cloud_connected": cloud.is_connected(active),
        "cloud_configured": cloud.is_configured(active) if info and info.auth_type == "oauth" else True,
        "cloud_email": cloud.connected_account(active),
        "cloud_supports_upload": cloud.supports_upload(active),
        "google_oauth_bundled": is_google_oauth_bundled(),
    }


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.secret_key = SECRET_KEY

    @app.context_processor
    def inject_globals():
        ctx = _cloud_context()
        app_info = get_app_info()
        ctx.update(
            {
                "app_name": app_info["app_name"],
                "app_version": app_info["app_version"],
                "app_author": app_info["app_author"],
                "app_year": app_info["app_year"],
                "app_developer_url": app_info["app_developer_url"],
                "app_developer_label": app_info["app_developer_label"],
                "default_expiry_days": store.get_default_expiry_days(),
                "default_expiry_value": store.get_default_expiry()[0],
                "default_expiry_unit": store.get_default_expiry()[1],
                "format_duration": format_duration,
                "format_time_remaining": format_time_remaining,
                "qr_themes": QR_THEMES,
                "logo_placements": LOGO_PLACEMENTS,
                "border_styles": BORDER_STYLES,
            }
        )
        return ctx

    @app.get("/")
    def dashboard():
        process_expired_shares(store, cloud)
        folders = store.list_folders()
        shares = store.list_links()
        force_update = request.args.get("check_updates") in ("1", "true", "yes")
        if force_update:
            clear_update_cache(store)
        update_info = check_for_update(store, force=force_update)
        return render_template(
            "dashboard.html",
            folders=folders,
            shares=shares,
            update_info=update_info,
            format_expiry=format_expiry,
            build_share_url=lambda link_id: build_share_url(BASE_URL, link_id),
            today_iso=date.today().isoformat(),
        )

    @app.post("/updates/check")
    def check_updates_route():
        clear_update_cache(store)
        info = check_for_update(store, force=True)
        if info is None:
            flash(
                "Could not check for updates. Confirm the GitHub repo is public and has a Release.",
                "error",
            )
        elif info.available:
            flash(
                f"Update available: v{info.latest_version}. See the banner on the dashboard.",
                "success",
            )
        else:
            flash(f"You are up to date (v{get_app_info()['app_version']}).", "success")
        return redirect(url_for("dashboard"))

    @app.get("/settings/branding/<kind>.png")
    def branding_asset(kind: str):
        if kind not in ("logo", "border"):
            abort(404)
        branding = store.get_branding()
        path = Path(branding.get(f"{kind}_path", ""))
        if not path.exists():
            abort(404)
        return send_file(path, mimetype="image/png")

    @app.get("/settings")
    def settings():
        active = cloud.get_active_provider_id()
        oauth_ready = {
            pid: cloud.is_configured(pid)
            for pid in ("google_drive", "dropbox", "onedrive")
        }
        default_value, default_unit = store.get_default_expiry()
        min_expiry, max_expiry = expiry_limits(default_unit)
        selected_info = PROVIDERS.get(active)
        show_oauth_advanced = bool(
            selected_info
            and selected_info.auth_type == "oauth"
            and (active != "google_drive" or not is_google_oauth_bundled())
        )
        return render_template(
            "settings.html",
            default_expiry_days=store.get_default_expiry_days(),
            default_expiry_value=default_value,
            default_expiry_unit=default_unit,
            min_expiry=min_expiry,
            max_expiry=max_expiry,
            min_days=MIN_EXPIRY_DAYS,
            max_days=MAX_EXPIRY_DAYS,
            selected_provider=active,
            oauth_ready=oauth_ready,
            google_oauth_bundled=is_google_oauth_bundled(),
            show_oauth_advanced=show_oauth_advanced,
            email_intro_text=store.get_email_intro_text()
            or default_email_intro(store.get_email_sender_name() or default_sender_name()),
            branding=store.get_branding(),
            logo_exists=bool(
                store.get_branding().get("logo_path")
                and Path(store.get_branding()["logo_path"]).exists()
            ),
            border_exists=bool(
                store.get_branding().get("border_path")
                and Path(store.get_branding()["border_path"]).exists()
            ),
        )

    @app.post("/settings")
    def save_settings():
        try:
            duration = parse_expiry_form(request.form, prefix="default_expiry")
            default_value = int(request.form.get("default_expiry_value", store.get_default_expiry()[0]))
            default_unit = request.form.get("default_expiry_unit", store.get_default_expiry()[1])
            _ = duration
        except ExpiryError as exc:
            flash(str(exc), "error")
            return redirect(url_for("settings"))

        provider = request.form.get("cloud_provider", cloud.get_active_provider_id())
        if provider in PROVIDERS:
            cloud.set_active_provider(provider)

        store.set_default_expiry(default_value, default_unit)

        sender_name = (request.form.get("email_sender_name") or "").strip()
        intro_text = (request.form.get("email_intro_text") or "").strip()
        # Keep any previously saved sender name; intro text is the visible email customisation.
        store.set_email_preferences(sender_name or store.get_email_sender_name(), intro_text)

        logo_placement = (request.form.get("logo_placement") or "none").strip().lower()
        if logo_placement not in LOGO_PLACEMENTS:
            logo_placement = "none"
        border_style = (request.form.get("border_style") or "none").strip().lower()
        if border_style not in BORDER_STYLES:
            border_style = "none"

        branding_dir = default_branding_dir()
        current = store.get_branding()
        logo_path = current.get("logo_path", "")
        border_path = current.get("border_path", "")
        clear_logo = request.form.get("clear_logo") == "on"
        clear_border = request.form.get("clear_border") == "on"

        try:
            logo_file = request.files.get("logo_png")
            if logo_file and logo_file.filename:
                dest = branding_dir / "logo.png"
                save_png_upload(logo_file, dest, kind="logo")
                logo_path = str(dest)
                if logo_placement == "none":
                    logo_placement = "center"
            elif clear_logo:
                if logo_path:
                    Path(logo_path).unlink(missing_ok=True)
                logo_path = ""
                logo_placement = "none"

            border_file = request.files.get("border_png")
            if border_style == "custom":
                if border_file and border_file.filename:
                    dest = branding_dir / "border.png"
                    save_png_upload(border_file, dest, kind="border")
                    border_path = str(dest)
                elif clear_border:
                    if border_path:
                        Path(border_path).unlink(missing_ok=True)
                    border_path = ""
                elif not border_path or not Path(border_path).exists():
                    raise QrAssetError(
                        "Upload a PNG border file for Custom border, or choose a built-in border."
                    )
            else:
                if clear_border and border_path:
                    Path(border_path).unlink(missing_ok=True)
                border_path = ""

            store.set_branding(
                logo_placement=logo_placement if logo_path else "none",
                border_style=border_style,
                logo_path=logo_path,
                border_path=border_path,
            )
        except QrAssetError as exc:
            flash(str(exc), "error")
            return redirect(url_for("settings"))

        client_id = (request.form.get("oauth_client_id") or "").strip()
        client_secret = (request.form.get("oauth_client_secret") or "").strip()
        if client_id and client_secret and provider in ("google_drive", "dropbox", "onedrive"):
            try:
                cloud.save_oauth_settings(provider, client_id, client_secret)
                flash("Cloud app credentials saved.", "success")
            except CloudProviderError as exc:
                flash(str(exc), "error")

        flash(f"Settings saved. Active cloud: {PROVIDERS[provider].name}. Default expiry: {format_duration(default_value, default_unit)}.", "success")
        return redirect(url_for("settings"))

    @app.post("/cloud/select")
    def select_cloud_provider():
        provider = request.form.get("provider", "")
        if provider not in PROVIDERS:
            flash("Choose a valid cloud provider.", "error")
            return redirect(request.referrer or url_for("dashboard"))
        cloud.set_active_provider(provider)
        flash(f"Using {PROVIDERS[provider].name}.", "success")
        return redirect(request.referrer or url_for("dashboard"))

    @app.get("/auth/<provider>")
    def auth_provider(provider: str):
        if provider not in PROVIDERS or PROVIDERS[provider].auth_type != "oauth":
            flash("This cloud provider does not use sign-in.", "error")
            return redirect(url_for("dashboard"))
        if not cloud.is_configured(provider):
            if provider == "google_drive" and is_google_oauth_bundled():
                flash("Google sign-in is not available in this build. Contact the app author.", "error")
            else:
                flash(f"Set up {PROVIDERS[provider].name} credentials in Settings first.", "error")
            return redirect(url_for("settings"))
        try:
            redirect_uri = url_for("auth_provider_callback", provider=provider, _external=True)
            return redirect(cloud.get_auth_url(provider, redirect_uri=redirect_uri))
        except CloudProviderError as exc:
            flash(str(exc), "error")
            return redirect(url_for("settings"))
        except Exception as exc:
            flash(f"Could not start sign-in: {exc}", "error")
            return redirect(url_for("settings"))

    @app.get("/auth/<provider>/callback")
    def auth_provider_callback(provider: str):
        if provider not in PROVIDERS:
            return redirect(url_for("dashboard"))

        oauth_error = request.args.get("error")
        if oauth_error:
            if oauth_error == "redirect_uri_mismatch":
                flash(
                    "Google redirect URI mismatch. In Google Cloud Console → Credentials → your OAuth client, "
                    "add BOTH redirect URIs shown in Settings, then try again.",
                    "error",
                )
            elif oauth_error == "access_denied" and provider == "google_drive":
                flash(
                    "Google blocked sign-in (403 access_denied). Your OAuth app is likely in "
                    "Testing mode — add your Gmail under Google Cloud Console → OAuth consent screen "
                    "→ Test users, then try again.",
                    "error",
                )
            else:
                detail = request.args.get("error_description") or oauth_error
                flash(f"Sign-in cancelled or denied: {detail}", "error")
            return redirect(url_for("settings"))

        try:
            redirect_uri = url_for("auth_provider_callback", provider=provider, _external=True)
            email = cloud.complete_auth(provider, request.url, redirect_uri=redirect_uri)
            flash(f"{PROVIDERS[provider].name} connected as {email or 'your account'}.", "success")
        except Exception as exc:
            message = str(exc)
            if "insecure_transport" in message:
                flash(
                    "Sign-in failed: local HTTP OAuth is blocked. Restart the app and try again.",
                    "error",
                )
            elif "code verifier" in message.lower() or "invalid_grant" in message.lower():
                flash(
                    "Sign-in session expired. Click Sign in with Google Drive again from the start.",
                    "error",
                )
            else:
                flash(f"Sign-in failed: {exc}", "error")
            return redirect(url_for("settings"))
        return redirect(url_for("dashboard"))

    @app.post("/auth/disconnect")
    def auth_disconnect():
        provider = request.form.get("provider") or cloud.get_active_provider_id()
        if provider in PROVIDERS and PROVIDERS[provider].auth_type == "oauth":
            cloud.disconnect(provider)
            flash(f"{PROVIDERS[provider].name} disconnected.", "success")
        return redirect(request.referrer or url_for("dashboard"))

    @app.post("/folders")
    def create_folder():
        name = (request.form.get("name") or "").strip()
        provider = request.form.get("provider") or cloud.get_active_provider_id()
        folder_url = (request.form.get("folder_url") or "").strip()

        if not name:
            flash("Folder name is required.", "error")
            return redirect(url_for("dashboard"))
        if provider not in PROVIDERS:
            flash("Choose a valid cloud provider.", "error")
            return redirect(url_for("dashboard"))

        try:
            if provider == "cloud_link":
                if not folder_url:
                    flash("Paste your cloud folder URL.", "error")
                    return redirect(url_for("dashboard"))
                created = cloud.create_folder(name, provider_id=provider, folder_url=folder_url)
            else:
                if not cloud.is_connected(provider):
                    flash(f"Sign in to {PROVIDERS[provider].name} first.", "error")
                    return redirect(url_for("dashboard"))
                created = cloud.create_folder(name, provider_id=provider)

            folder = store.create_folder(
                name=name,
                drive_folder_id=created.remote_id,
                drive_url=created.share_url,
                provider=provider,
            )
            flash(f'Folder "{name}" created with {PROVIDERS[provider].name}.', "success")
            return redirect(url_for("folder_detail", folder_id=folder.id))
        except CloudProviderError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

    @app.get("/folders/<folder_id>")
    def folder_detail(folder_id: str):
        process_expired_shares(store, cloud)
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)
        files = []
        provider_info = PROVIDERS.get(folder.provider)
        if provider_info and provider_info.supports_upload:
            try:
                files = cloud.list_files(folder.provider, folder.drive_folder_id)
            except CloudProviderError as exc:
                flash(str(exc), "error")
        shares = store.list_links(folder_id=folder_id)
        default_value, default_unit = store.get_default_expiry()
        min_expiry, max_expiry = expiry_limits(default_unit)
        return render_template(
            "folder.html",
            folder=folder,
            files=files,
            shares=shares,
            provider_info=provider_info,
            format_expiry=format_expiry,
            format_time_remaining=format_time_remaining,
            default_expiry_value=default_value,
            default_expiry_unit=default_unit,
            min_expiry=min_expiry,
            max_expiry=max_expiry,
            build_share_url=lambda link_id: build_share_url(BASE_URL, link_id),
        )

    @app.post("/folders/<folder_id>/upload")
    def upload_files(folder_id: str):
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)
        provider_info = PROVIDERS.get(folder.provider)
        if not provider_info or not provider_info.supports_upload:
            flash("Upload is not available for this folder type.", "error")
            return redirect(url_for("folder_detail", folder_id=folder_id))

        uploads = request.files.getlist("files")
        if not uploads:
            flash("Choose at least one file to upload.", "error")
            return redirect(url_for("folder_detail", folder_id=folder_id))

        uploaded = 0
        branded_count = 0
        errors: list[str] = []
        branding = store.get_branding()
        for item in uploads:
            if not item or not item.filename:
                continue
            content = item.read()
            if not content:
                continue
            filename = item.filename
            mime_type = item.mimetype or "application/octet-stream"
            try:
                branded_bytes, branded_mime = brand_image_bytes(
                    content,
                    filename,
                    logo_path=branding.get("logo_path") or None,
                    logo_placement=branding.get("logo_placement", "none"),
                    border_style=branding.get("border_style", "none"),
                    border_path=branding.get("border_path") or None,
                )
                if branded_mime:
                    content = branded_bytes
                    mime_type = branded_mime
                    # Keep a .png extension when we re-encode branded images.
                    stem = Path(filename).stem
                    filename = f"{stem}.png"
                    branded_count += 1
                cloud.upload_file(
                    folder.provider,
                    folder.drive_folder_id,
                    filename,
                    content,
                    mime_type,
                )
                uploaded += 1
            except Exception as exc:
                errors.append(f"{item.filename}: {exc}")

        if uploaded:
            if branded_count:
                flash(
                    f"Uploaded {uploaded} file(s) to {folder.name} "
                    f"({branded_count} image{'s' if branded_count != 1 else ''} branded).",
                    "success",
                )
            else:
                flash(f"Uploaded {uploaded} file(s) to {folder.name}.", "success")
        if errors:
            flash("Some uploads failed: " + "; ".join(errors[:3]), "error")
        if not uploaded and not errors:
            flash("Choose at least one file to upload.", "error")
        return redirect(url_for("folder_detail", folder_id=folder_id))

    @app.post("/folders/<folder_id>/files/<file_id>/delete")
    def delete_file_route(folder_id: str, file_id: str):
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)
        try:
            deleted, errors = delete_folder_files(cloud, folder, [file_id])
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("folder_detail", folder_id=folder_id))

        if deleted:
            flash("File deleted from cloud storage.", "success")
        if errors:
            flash(errors[0], "error")
        return redirect(url_for("folder_detail", folder_id=folder_id))

    @app.post("/folders/<folder_id>/files/delete")
    def bulk_delete_files_route(folder_id: str):
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)
        file_ids = request.form.getlist("file_ids")
        try:
            deleted, errors = delete_folder_files(cloud, folder, file_ids)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("folder_detail", folder_id=folder_id))

        if deleted:
            flash(
                f"Deleted {deleted} file{'s' if deleted != 1 else ''} from cloud storage.",
                "success",
            )
        if errors:
            flash("Some files could not be deleted: " + "; ".join(errors[:3]), "error")
        if not deleted and not errors:
            flash("Select at least one file to delete.", "error")
        return redirect(url_for("folder_detail", folder_id=folder_id))

    @app.post("/folders/<folder_id>/share")
    def share_folder(folder_id: str):
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)

        expiry_value = store.get_default_expiry()[0]
        expiry_unit = store.get_default_expiry()[1]
        try:
            duration = parse_expiry_form(request.form)
            expiry_value = int(request.form.get("expiry_value", expiry_value))
            expiry_unit = request.form.get("expiry_unit", expiry_unit)
        except ExpiryError as exc:
            flash(str(exc), "error")
            return redirect(url_for("folder_detail", folder_id=folder_id))

        theme = request.form.get("qr_theme", "canva-classic")
        branding = store.get_branding()
        logo_path = branding.get("logo_path", "")
        border_path = branding.get("border_path", "")
        logo_placement = branding.get("logo_placement", "none")
        border_style = branding.get("border_style", "none")
        if logo_path and not Path(logo_path).exists():
            logo_path = ""
            logo_placement = "none"
        if border_style == "custom" and (not border_path or not Path(border_path).exists()):
            border_style = "none"
            border_path = ""

        result = create_share(
            store,
            target_url=folder.drive_url,
            label=folder.name,
            folder=folder,
            expiry_duration=duration,
            qr_theme=theme,
            qr_logo_path=logo_path,
            qr_logo_placement=logo_placement if logo_path else "none",
            qr_border_style=border_style,
            qr_border_path=border_path if border_style == "custom" else "",
        )
        flash(
            format_share_expiry_message(
                result.link,
                value=expiry_value,
                unit=expiry_unit,
            ),
            "success",
        )
        return redirect(url_for("share_detail", link_id=result.link.id))

    @app.post("/folders/<folder_id>/delete")
    def delete_folder_route(folder_id: str):
        folder = store.get_folder(folder_id)
        if not folder:
            abort(404)
        delete_from_cloud = request.form.get("delete_from_cloud") == "on"
        try:
            message = delete_folder_record(
                store,
                cloud,
                folder_id,
                delete_from_cloud=delete_from_cloud,
            )
            flash(message, "success")
        except ValueError as exc:
            flash(str(exc), "error")
        # Always return to the dashboard — the folder page no longer exists.
        return redirect(url_for("dashboard"))

    @app.post("/shares/<link_id>/delete")
    def delete_share_route(link_id: str):
        link = store.get_link(link_id)
        if not link:
            abort(404)
        folder_id = link.folder_id
        try:
            message = delete_share_only(store, link_id)
            flash(message, "success")
        except ValueError as exc:
            flash(str(exc), "error")
        if folder_id and store.get_folder(folder_id):
            return redirect(url_for("folder_detail", folder_id=folder_id))
        return redirect(url_for("dashboard"))

    @app.post("/sync/refresh")
    def refresh_cloud_route():
        try:
            message = refresh_from_cloud(store, cloud)
            category = "info" if message.startswith("Everything is already") else "success"
            flash(message, category)
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/cleanup/bulk")
    def bulk_cleanup_route():
        try:
            from_date = parse_date_field(request.form.get("from_date", ""), "From date")
            to_date = parse_date_field(request.form.get("to_date", ""), "To date")
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

        delete_folders = request.form.get("delete_folders") == "on"
        delete_shares = request.form.get("delete_shares") == "on"
        delete_from_cloud = request.form.get("delete_from_cloud") == "on"

        try:
            message = bulk_delete_by_date(
                store,
                cloud,
                from_date=from_date,
                to_date=to_date,
                delete_folders=delete_folders,
                delete_shares=delete_shares,
                delete_from_cloud=delete_from_cloud,
            )
            category = "info" if message.startswith("No matching") else "success"
            flash(message, category)
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.get("/shares/<link_id>")
    def share_detail(link_id: str):
        link = store.get_link(link_id)
        if not link:
            abort(404)
        folder = store.get_folder(link.folder_id) if link.folder_id else None
        provider_info = PROVIDERS.get(folder.provider) if folder else None
        try:
            ensure_qr_image(
                link.id,
                target_url=link.target_url,
                label=link.label,
                theme=link.qr_theme,
                logo_path=link.qr_logo_path or None,
                logo_placement=link.qr_logo_placement,
                border_style=link.qr_border_style,
                border_path=link.qr_border_path or None,
            )
            qr_available = True
        except Exception:
            qr_available = default_qr_path(link.id).exists()
        return render_template(
            "share.html",
            link=link,
            folder=folder,
            provider_info=provider_info,
            share_url=build_share_url(BASE_URL, link.id),
            qr_available=qr_available,
            format_expiry=format_expiry,
            email_intro_text=store.get_email_intro_text()
            or default_email_intro(store.get_email_sender_name() or default_sender_name()),
        )

    @app.post("/shares/<link_id>/compose-email")
    def compose_share_email_route(link_id: str):
        link = store.get_link(link_id)
        if not link:
            abort(404)
        if not link.is_available:
            flash("This share is no longer active.", "error")
            return redirect(url_for("share_detail", link_id=link_id))

        to_email = (request.form.get("recipient_email") or "").strip()
        intro_text = (request.form.get("email_intro_text") or "").strip()
        share_url = build_share_url(BASE_URL, link.id)
        try:
            mailto_url, gmail_url, _subject = compose_share_email(
                to_email=to_email,
                link=link,
                share_url=share_url,
                sender_label=store.get_email_sender_name() or default_sender_name(),
                intro_text=intro_text or None,
            )
        except EmailComposeError as exc:
            flash(str(exc), "error")
            return redirect(url_for("share_detail", link_id=link_id))

        return render_template(
            "compose_email.html",
            link_id=link_id,
            recipient=to_email,
            mailto_url=mailto_url,
            gmail_url=gmail_url,
        )

    @app.get("/qr/<link_id>.png")
    def qr_image(link_id: str):
        link = store.get_link(link_id)
        if not link:
            abort(404)
        try:
            path = ensure_qr_image(
                link.id,
                target_url=link.target_url,
                label=link.label,
                theme=link.qr_theme,
                logo_path=link.qr_logo_path or None,
                logo_placement=link.qr_logo_placement,
                border_style=link.qr_border_style,
                border_path=link.qr_border_path or None,
            )
        except Exception:
            path = default_qr_path(link_id)
            if not path.exists():
                abort(404)
        as_download = request.args.get("download") in ("1", "true", "yes")
        return send_file(
            path,
            mimetype="image/png",
            as_attachment=as_download,
            download_name=f"share_{link_id}.png" if as_download else None,
        )

    @app.post("/shares/<link_id>/revoke")
    def revoke_share_route(link_id: str):
        link = store.get_link(link_id)
        if not link:
            abort(404)
        try:
            message = revoke_share(store, cloud, link_id)
            flash(message, "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.get("/s/<link_id>")
    def resolve_share(link_id: str):
        process_expired_shares(store, cloud)
        link = store.get_link(link_id)
        if not link:
            return NOT_FOUND_HTML, 404
        if not link.is_available:
            return EXPIRED_HTML, 410
        return redirect(link.target_url, code=302)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


def run_server() -> None:
    app = create_app()
    print(f"QRFileshare running at {BASE_URL}")
    print("Connect cloud storage from the app to create and share folders.")
    app.run(host=HOST, port=PORT, debug=FLASK_DEBUG, use_reloader=False)


if __name__ == "__main__":
    run_server()
