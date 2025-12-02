import os
from django.core.management.base import BaseCommand
from whatsappapi.moderation import evaluate_content


class Command(BaseCommand):
    help = "Run AI-only moderation on a small set of legal/illegal samples to verify gating."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Limit number of samples per category')

    def handle(self, *args, **options):
        # Force AI-only gate for this smoke test
        os.environ['AI_ONLY_GATE'] = 'true'

        legal_samples = [
            "Hello, this is a legal promotional message about our product.",
            "Join our webinar on productivity hacks. Family-friendly and non-violent.",
            "Contact support if you need assistance; no illegal content or hate.",
        ]
        illegal_samples = [
            # Examples aligned with existing tests
            "We should lynch Muslims",
            "Kill all gays",
            "dark web , banned videos available",
            "Visit the dark web market, banned content available",
            "Buy cocaine wholesale",
            "AK-47 available for sale",
        ]

        limit = int(options.get('limit') or 0)
        if limit > 0:
            legal_samples = legal_samples[:limit]
            illegal_samples = illegal_samples[:limit]

        self.stdout.write(self.style.WARNING("AI-only moderation smoke test"))

        def _print_result(label, text):
            res = evaluate_content(text)
            blocked = bool(res.get('blocked'))
            review = bool(res.get('requires_review'))
            score = int(res.get('risk_score') or 0)
            reasons = ', '.join(res.get('reasons') or [])
            status = 'BLOCKED' if blocked else ('REVIEW' if review else 'ALLOWED')
            self.stdout.write(f"[{label}] {status} (score={score}) reasons=[{reasons}] text={text}")

        for s in legal_samples:
            _print_result('LEGAL', s)
        for s in illegal_samples:
            _print_result('ILLEGAL', s)

        self.stdout.write(self.style.SUCCESS("Done."))