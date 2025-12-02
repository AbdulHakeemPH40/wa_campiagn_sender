from django.core.management.base import BaseCommand
from django.conf import settings
import requests
import time


class Command(BaseCommand):
    help = "Ping OpenAI Moderations API to verify connectivity and permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--text",
            default="I want to kill them.",
            help="Text to send to the moderations endpoint for a quick check.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=getattr(settings, "AI_TIMEOUT", 8),
            help="Request timeout in seconds.",
        )
        parser.add_argument(
            "--retries",
            type=int,
            default=2,
            help="Number of retries on 429 rate limits (default: 2).",
        )
        parser.add_argument(
            "--backoff",
            type=float,
            default=0.75,
            help="Initial backoff seconds for 429; doubles each retry (default: 0.75).",
        )
        parser.add_argument(
            "--project",
            default=None,
            help="Optional OpenAI Project ID to include via 'OpenAI-Project' header.",
        )

    def handle(self, *args, **options):
        text = options["text"]
        timeout = options["timeout"]
        retries = max(0, options.get("retries", 2))
        backoff = float(options.get("backoff", 0.75))
        project_id = options.get("project")

        provider = getattr(settings, "AI_PROVIDER", "openai")
        if provider != "openai":
            self.stdout.write(
                self.style.WARNING(
                    f"AI_PROVIDER is '{provider}'. This command tests only OpenAI moderations."
                )
            )

        api_key = getattr(settings, "OPENAI_API_KEY", None)
        url = getattr(
            settings,
            "OPENAI_MODERATION_URL",
            "https://api.openai.com/v1/moderations",
        )
        model = getattr(settings, "OPENAI_MODERATION_MODEL", None)

        if not api_key:
            self.stderr.write(
                self.style.ERROR("OPENAI_API_KEY is not configured in settings.")
            )
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if project_id:
            headers["OpenAI-Project"] = project_id

        payload = {"input": text}
        if model:
            payload["model"] = model

        self.stdout.write(
            f"POST {url} with timeout={timeout}s (model={model or 'default'})"
        )

        attempts = retries + 1
        for attempt in range(1, attempts + 1):
            start = time.time()
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.ERROR(f"Request error: {e}"))
                return
            duration_ms = int((time.time() - start) * 1000)

            self.stdout.write(
                f"Status: {resp.status_code} in {duration_ms} ms (attempt {attempt}/{attempts})"
            )

            # Interpret common outcomes
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    results = data.get("results", [])
                    flagged = results[0].get("flagged") if results else None
                    scores = results[0].get("category_scores", {}) if results else {}
                    top = ", ".join(
                        [
                            f"{k}:{round(v, 3)}" for k, v in sorted(
                                scores.items(), key=lambda x: x[1], reverse=True
                            )[:5]
                        ]
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"OK. flagged={flagged}. top categories: {top or 'n/a'}"
                        )
                    )
                except Exception:
                    self.stdout.write(self.style.SUCCESS("OK. Response parsed."))
                return

            if resp.status_code == 429:
                # Rate limited; respect Retry-After if present, else exponential backoff
                retry_after = resp.headers.get("Retry-After")
                req_id = resp.headers.get("x-request-id")
                # Collect any rate-limit headers if provided
                rl_headers = {
                    k: v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")
                }
                details = None
                try:
                    details = resp.json()
                except Exception:
                    details = resp.text

                self.stderr.write(
                    self.style.WARNING(
                        f"429 Too Many Requests. request_id={req_id or 'n/a'} retry_after={retry_after or 'n/a'} rl={rl_headers or 'n/a'}"
                    )
                )
                if attempt < attempts:
                    wait = float(retry_after) if retry_after else round(backoff * (2 ** (attempt - 1)), 2)
                    self.stdout.write(f"Waiting {wait}s before retry {attempt + 1}/{attempts}...")
                    time.sleep(wait)
                    continue
                else:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Final attempt failed with 429. Details: {details}"
                        )
                    )
                    return

            if resp.status_code in (401, 403):
                # 401: bad or missing key; 403: project/key lacks permission
                details = None
                try:
                    details = resp.json()
                except Exception:
                    details = resp.text
                self.stderr.write(
                    self.style.ERROR(
                        f"{resp.status_code} error calling moderations. Details: {details}"
                    )
                )
                if resp.status_code == 403:
                    self.stderr.write(
                        self.style.WARNING(
                            "Check key permissions. If 'Moderations' isn't visible, temporarily set the key to 'All', test, then revert to 'Restricted' and keep only needed permissions."
                        )
                    )
                return

            # Other unexpected responses
            body = resp.text
            self.stderr.write(
                self.style.ERROR(
                    f"Unexpected response ({resp.status_code}): {body[:400]}"
                )
            )
            return