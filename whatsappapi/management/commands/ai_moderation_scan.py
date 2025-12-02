import os
import re
import csv
import json
from typing import List, Dict
from django.core.management.base import BaseCommand, CommandParser
from whatsappapi.moderation import evaluate_content


class Command(BaseCommand):
    help = "Scan a text file and track AI moderation results per line."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--file",
            required=True,
            help="Path to a UTF-8 text file containing one test case per line",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Optional output path (CSV or JSON) to save results",
        )
        parser.add_argument(
            "--format",
            choices=["csv", "json"],
            default="csv",
            help="Output format when --output is provided (default: csv)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process at most N lines (0 = all)",
        )
        parser.add_argument(
            "--ai-only",
            action="store_true",
            help="Force AI-only gate (treat review as block in UI gate)",
        )

    def handle(self, *args, **options):
        path = str(options.get("file") or "").strip()
        output = options.get("output")
        out_fmt = str(options.get("format") or "csv").lower()
        limit = int(options.get("limit") or 0)
        ai_only = bool(options.get("ai_only"))

        if ai_only:
            os.environ["AI_ONLY_GATE"] = "true"

        if not path:
            self.stderr.write(self.style.ERROR("--file is required"))
            return
        if not os.path.exists(path):
            self.stderr.write(self.style.ERROR(f"File not found: {path}"))
            return

        # Read lines
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln.strip() for ln in f.readlines()]

        if limit > 0:
            lines = lines[:limit]

        self.stdout.write(self.style.WARNING(
            f"Scanning {len(lines)} lines from {path} (AI-only={ai_only})"
        ))

        # Helper to infer expected label from text prefix
        def _infer_expected_label(text: str) -> str:
            t = (text or "").strip()
            m = re.match(r"^(legal|illegal|borderline)\b", t, flags=re.IGNORECASE)
            if m:
                return m.group(1).lower()
            # Look for common marker words as a fallback
            if re.search(r"\bborderline\b", t, flags=re.IGNORECASE):
                return "borderline"
            if re.search(r"\billegal\b", t, flags=re.IGNORECASE):
                return "illegal"
            if re.search(r"\blegal\b", t, flags=re.IGNORECASE):
                return "legal"
            return ""

        results: List[Dict] = []

        for idx, text in enumerate(lines, start=1):
            if not text:
                continue
            res = evaluate_content(text)
            blocked = bool(res.get("blocked"))
            review = bool(res.get("requires_review"))
            score = int(res.get("risk_score") or 0)
            reasons = res.get("reasons") or []
            urls = res.get("urls") or []
            decision = int(res.get("decision", 1))
            hits = res.get("policy_hits") or []
            matches = ";".join([f"{h.get('category')}:{h.get('match')}" for h in hits])
            status = "blocked" if blocked else ("review" if review else "allowed")
            expected = _infer_expected_label(text)
            # Print concise line
            self.stdout.write(
                f"[{idx}] expected={expected or '-'} status={status} decision={decision} score={score} "
                f"reasons={','.join(map(str, reasons))} matches={matches}"
            )
            results.append({
                "index": idx,
                "expected": expected,
                "status": status,
                "decision": decision,
                "risk_score": score,
                "reasons": reasons,
                "urls": urls,
                "policy_hits": hits,
                "text": text,
            })

        # Save output if requested
        if output:
            try:
                if out_fmt == "json":
                    with open(output, "w", encoding="utf-8") as jf:
                        json.dump(results, jf, ensure_ascii=False, indent=2)
                    self.stdout.write(self.style.SUCCESS(f"Saved JSON: {output}"))
                else:
                    # csv
                    with open(output, "w", encoding="utf-8", newline="") as cf:
                        writer = csv.writer(cf)
                        writer.writerow([
                            "index", "expected", "status", "decision", "risk_score", "reasons", "policy_hits", "urls", "text"
                        ])
                        for r in results:
                            writer.writerow([
                                r["index"], r["expected"], r["status"], r["decision"], r["risk_score"],
                                ";".join(map(str, r["reasons"])), ";".join([f"{h.get('category')}:{h.get('match')}" for h in (r.get("policy_hits") or [])]),
                                ";".join(map(str, r["urls"])), r["text"]
                            ])
                    self.stdout.write(self.style.SUCCESS(f"Saved CSV: {output}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to write output: {e}"))

        self.stdout.write(self.style.SUCCESS("Done."))