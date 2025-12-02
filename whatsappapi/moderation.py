import re
import os
import time
import json
import hashlib
import logging
from typing import Dict, List, Tuple, Optional

# Prefer Django settings for configuration if available; fall back to env vars
try:
    from django.conf import settings as django_settings  # type: ignore
except Exception:
    django_settings = None

logger = logging.getLogger(__name__)

# Disclaimer downgrade toggle — default ON (disable) to keep AI strictly authoritative
_downgrade_val = os.environ.get('DISABLE_DISCLAIMER_DOWNGRADE', None)
if _downgrade_val is None and django_settings is not None:
    _downgrade_val = getattr(django_settings, 'DISABLE_DISCLAIMER_DOWNGRADE', 'true')
DISABLE_DISCLAIMER_DOWNGRADE: bool = str(_downgrade_val or '').lower() in {'1', 'true', 'yes'}

URL_REGEX = re.compile(r"https?://[\w\-\.]+(?:/[\w\-\./?%&=]*)?", re.IGNORECASE)

# Leetspeak/obfuscation normalization map
_LEET_TRANSLATION = str.maketrans({
    '0': 'o', '1': 'l', '3': 'e', '4': 'a', '5': 's', '7': 't',
    '@': 'a', '$': 's', '!': 'i'
})



def _get_safe_finance_domains() -> List[str]:
    """Return an allowlist of official finance/bank domains.

    Configurable via Django settings SAFE_FINANCE_DOMAINS or env SAFE_FINANCE_DOMAINS.
    Comma-separated list, e.g.: "unitybank.in,hdfcbank.com,icicibank.com".
    """
    try:
        val = os.environ.get('SAFE_FINANCE_DOMAINS', None)
        if val is None and django_settings is not None:
            val = getattr(django_settings, 'SAFE_FINANCE_DOMAINS', '')
        items = [d.strip().lower() for d in (val or '').split(',') if (d or '').strip()]
        # Provide sensible defaults if unset
        if not items:
            items = [
                'unitybank.in', 'sbi.co.in', 'icicibank.com', 'hdfcbank.com',
                'axisbank.com', 'kotak.com'
            ]
        return items
    except Exception:
        return []


def _extract_host(url: str) -> str:
    try:
        m = re.match(r"https?://([^/\s]+)", url.strip(), flags=re.IGNORECASE)
        return (m.group(1) or '').lower() if m else ''
    except Exception:
        return ''


def _urls_in_finance_allowlist(urls: List[str]) -> bool:
    """True if all URLs are in the finance allowlist domains (or there are no URLs)."""
    try:
        if not urls:
            return True
        allow = _get_safe_finance_domains()
        for u in urls:
            host = _extract_host(u)
            if not host:
                return False
            # Allow subdomains of allowed domains
            if not any(host == d or host.endswith('.' + d) for d in allow):
                return False
        return True
    except Exception:
        return False


def _has_shortener_or_messaging_link(urls: List[str]) -> bool:
    """Detect risky link hosts like shorteners or messaging jump links."""
    risky = {
        'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly', 'is.gd',
        'wa.me', 'web.whatsapp.com', 'chat.whatsapp.com', 't.me', 'telegram.me',
    }
    try:
        for u in urls or []:
            host = _extract_host(u)
            if any(host == r or host.endswith('.' + r) for r in risky):
                return True
        return False
    except Exception:
        return True


def _is_legitimate_banking_notice(text: str, urls: List[str]) -> bool:
    """Heuristic to detect non-promotional, transactional banking/loan notifications.

    Targets messages like: "Loan sanctioned/approved", "Funds on the way",
    "View status", etc., from a bank/NBFC. Reject if promotional/suspicious.
    """
    t = (text or '').lower()
    try:
        # STRICT mode: require at least 2 of these conditions:
        # 1. Bank/financial entity mention
        # 2. Loan-related keywords
        # 3. Transaction status keywords (approved, funds on way, disbursed)
        # 4. Amount/currency mention (₹, $, USD, INR, etc.)
        
        bank_like = bool(re.search(r"\b(bank|nbfc|finance|financial\s+services|incred|lender|creditor)\b", t))
        loan_like = bool(re.search(r"\b(loan|credit\s+line|home\s+loan|car\s+loan|personal\s+loan|emi|credit|borrowing)\b", t))
        status_like = bool(re.search(r"\b(approved|sanctioned|disburs(e|al|ed)|funds\s+on\s+the\s+way|view\s+status|track|statement|receipt|officially)\b", t))
        amount_like = bool(re.search(r"[₹\$£€¥]|\b(rs|usd|inr|pound|euro|yen)\b|\d+[,\d]*\s*(thousand|lakh|crore|million|billion)", t))
        
        # Count matching conditions
        conditions_met = sum([bank_like, loan_like, status_like, amount_like])
        
        # REJECT if clearly promotional or scam-like
        risky_claims = [
            r"\binstant\b", r"\bguarantee(d)?\b", r"no\s*doc(ument)?s", r"zero\s*docs",
            r"apply\s*now", r"limited\s*time", r"cheap\s*loan", r"lowest\s*interest\s*now",
            r"dm\b|\bmessage\s+me\b|\bwhatsapp\b|\btelegram\b|\bcall\s+now\b",  # Exclude generic "contact"
            r"pay\s*(fee|charges)\s*(first|upfront)", r"processing\s*fee\s*(first|upfront)",
            r"upi\b|gpay\b|paytm\b|phonepe\b",  # Payment apps (scam indicator)
        ]
        has_risky_claim = any(re.search(p, t, flags=re.IGNORECASE) for p in risky_claims)
        
        # Link checks: allow if none or all in allowlist, and no shorteners/messaging jumps
        links_ok = _urls_in_finance_allowlist(urls) and (not _has_shortener_or_messaging_link(urls))
        
        # Decision: need at least 2 conditions AND no risky claims AND clean links
        is_legitimate = conditions_met >= 2 and (not has_risky_claim) and links_ok
        
        if is_legitimate:
            logger.info(f"_is_legitimate_banking_notice: ALLOWED (conditions_met={conditions_met}, bank={bank_like}, loan={loan_like}, status={status_like}, amount={amount_like})")
        return is_legitimate
    except Exception as e:
        logger.warning(f"_is_legitimate_banking_notice exception: {e}")
        return False


def _normalize_text(text: str) -> str:
    s = (text or '').lower()
    return s.translate(_LEET_TRANSLATION)



def _has_non_violence_disclaimer(text: str) -> bool:
    """Detect phrases explicitly forbidding violence to avoid false AI blocks.

    Matches common forms such as "non‑violent", "avoid violence/harm/fighting/threats",
    "family-friendly", and similar. Handles punctuation or special hyphens between words.
    """
    t = (text or '').lower()
    patterns = [
        r"\bnon[\W_]*violent\b",
        r"\bavoid\b[^\n]{0,60}\bviolence\b",
        r"\bavoid\b[^\n]{0,60}\bharm\b",
        r"\bavoid\b[^\n]{0,60}\bfighting\b",
        r"\bavoid\b[^\n]{0,60}\bthreats?\b",
        r"\bno\b[^\n]{0,60}\bharm\b",
        r"\bno\b[^\n]{0,60}\bfighting\b",
        r"\bno\b[^\n]{0,60}\bthreats?\b",
        r"\bfamily[\W_]*friendly\b",
        r"\bsafe\b[^\n]{0,60}\btone\b",
    ]
    for p in patterns:
        try:
            if re.search(p, t, flags=re.IGNORECASE):
                return True
        except Exception:
            # If regex fails, skip and continue
            continue
    return False


def _has_offer_promotion(text: str) -> bool:
    """Detect explicit offer/sale/promotion language.

    Examples: for sale, available, buy, order, price, DM, link, download,
    shipping, delivery, subscribe, join, contact now.
    """
    t = (text or '').lower()
    patterns = [
        r"\bfor\s+sale\b",
        r"\bavailable\b",
        r"\bbuy\b",
        r"\border\b",
        r"\bprice\b",
        r"\bdm\b|\bpm\b|\bmessage\s+me\b",
        r"\blink\b|\bdownload\b|\burl\b",
        r"\bshipping\b|\bdelivery\b|\bdiscreet\s+shipping\b",
        r"\bsubscribe\b|\bjoin\b",
        r"\bcontact\s+now\b|\bcontact\b",
        r"\bget\s+now\b|\bgrab\b|\boffer\b",
    ]
    for p in patterns:
        try:
            if re.search(p, t, flags=re.IGNORECASE):
                return True
        except Exception:
            continue
    return False


def _is_reporting_context(text: str) -> bool:
    """Detect investigation/reporting-to-authorities context.

    Examples: inform police, report to police/authorities, investigate, illegal activities,
    need to inform, we need investigate, complaint, evidence, found, discovered,
    medical emergency, treatment, therapy, rehabilitation, helpline,
    investigative, breaking news, news, journalism, museum, historical, academic, study, research.
    """
    t = (text or '').lower()
    patterns = [
        r"\binform\s+police\b",
        r"\breport\s+(to\s+)?police\b",
        r"\breport\s+(to\s+)?authorit(y|ies)\b",
        r"\binvestigat(e|ion)\b",
        r"\billegal\s+activit(y|ies)\b",
        r"\billegal\s+content\b",
        r"\bneed\s+to\s+inform\b|\bneed\s+inform\b",
        r"\bcomplain(t)?\b",
        r"\bevidence\b",
        r"\bfound\b",
        r"\bdiscovered?\b",
        r"\breport\s+(this|it|the)\b",
        r"\bawareness\b",
        # Medical context patterns
        r"\bmedical\s+emergency\b",
        r"\bemergency\b",
        r"\btreatment\b",
        r"\btherapy\b",
        r"\brehabilitation\b|\brehab\b",
        r"\bhelpline\b",
        r"\bsupport\s+group\b",
        # News/Journalism context patterns
        r"\binvestigative\b",
        r"\breaking\s+news\b",
        r"\bnews\b",
        r"\bjournalism\b",
        # Academic/Historical context patterns
        r"\bmuseum\b",
        r"\bhistoric(al)?\b",
        r"\bacademic\b",
        r"\bstudy\b",
        r"\bresearch\b",
        r"\bexhibit(ion)?\b",
    ]
    for p in patterns:
        try:
            if re.search(p, t, flags=re.IGNORECASE):
                return True
        except Exception:
            continue
    return False


def evaluate_content(text: str, attachment_type: str = None) -> Dict:
    """
    Pure AI-only content moderation for WhatsApp campaigns.
    Returns a dict with risk_score, blocked, requires_review, reasons.
    """
    if not text:
        return {"risk_score": 0, "blocked": False, "requires_review": False, "reasons": [], "urls": []}

    normalized = _normalize_text(text)
    urls = URL_REGEX.findall(text or '')

    # Always use AI moderation (with caching). If AI unavailable, block as fail-safe.
    ai_res = None
    try:
        cache_key = hashlib.sha256((text or '').encode('utf-8')).hexdigest()
        ai_res = _ai_cache_get(cache_key)
        if ai_res is None:
            ai_res = _ai_evaluate_content(text)
            if ai_res:
                _ai_cache_set(cache_key, ai_res)
    except Exception:
        ai_res = None

    if not ai_res:
        return {
            "risk_score": 75,
            "blocked": True,
            "requires_review": True,
            "reasons": ["ai_unavailable"],
            "urls": urls,
        }

    ai_score = int(ai_res.get('risk_score', 0))
    ai_blocked = bool(ai_res.get('blocked'))
    ai_reasons = ai_res.get('reasons') or []

    # Downgrade AI 'violence' blocks to review when prompt explicitly forbids violence
    has_anti_violence = _has_non_violence_disclaimer(normalized)
    has_violence_reason = any('violence' in (str(r).lower()) for r in ai_reasons)

    blocked = ai_blocked
    requires_review = (ai_score >= 60 and not blocked)
    policy_hits: List[Dict] = []
    
    # Early check: if it's a legitimate banking notice, ALLOW immediately
    # This prevents the classifier from blocking legitimate loan notifications
    legit_bank_notice = _is_legitimate_banking_notice(normalized, urls)
    if legit_bank_notice and not ai_blocked:
        # Legitimate banking/loan message - return allow immediately
        logger.info(f"Early exit: legitimate banking notice detected, allowing content")
        res = {
            "risk_score": max(0, ai_score - 20),  # Lower risk for banking
            "blocked": False,
            "requires_review": False,
            "reasons": [f"ai:{r}" for r in ai_reasons][:10],
            "urls": urls,
            "policy_hits": [{"match": "banking_notice_override"}],
            "decision": 1,  # ALLOW
        }
        return res
    
    # ... existing code ...
    # Optional secondary AI classifier (OpenAI chat) for illicit trade categories
    _clf_enabled_val = os.environ.get('AI_CLASSIFIER_ENABLED', None)
    if _clf_enabled_val is None and django_settings is not None:
        # Default to true: enable classifier to catch explicit illicit trade offers
        _clf_enabled_val = getattr(django_settings, 'AI_CLASSIFIER_ENABLED', 'true')
    classifier_enabled = str(_clf_enabled_val or '').lower() in {'1', 'true', 'yes'}

    # Manual policy overlays removed; AI-only moderation continues
    if False:
        pass
    if (not DISABLE_DISCLAIMER_DOWNGRADE) and blocked and has_violence_reason and has_anti_violence:
        blocked = False
        requires_review = True
        logger.info("AI moderation 'violence' downgraded to review due to explicit non-violence disclaimer")

    # Optional classifier: if AI did not block, run a small OpenAI chat classifier
    # to catch policy violations not always covered by Moderations.
    if classifier_enabled and (not blocked):
        try:
            cls = _ai_illicit_trade_classifier(text)
        except Exception:
            cls = None
        if cls:
            try:
                illegal = bool(cls.get('illegal_trade'))
                confidence = float(cls.get('confidence', 0.0))
                category = (cls.get('category') or 'illicit_trade')
            except Exception:
                illegal, confidence, category = False, 0.0, 'illicit_trade'
            # Hard-block categories
            hard_block_cats = {
                'weapon_trade', 'drug_trade', 'fraud_trade', 'sexual_minors',
                'adult_porn', 'unlawful_data', 'illegal_content_or_rights',
                'hate_speech', 'racism', 'color_discrimination',
                'violence_threat', 'blackmail_extortion',
                'human_trafficking', 'child_abuse', 'animal_abuse', 'gender_based_violence',
                'terrorism_extremism', 'war_promotion',
                'money_laundering', 'black_money', 'counterfeit_currency', 'counterfeit_documents',
                'hacking_services', 'doxing_tracking',
                'dark_web_illicit_content', 'banned_content_distribution'
            }
            # Review categories (treated as block in send gate when AI_ONLY_GATE=true)
            review_cats = {'gambling', 'alcohol', 'tobacco', 'misleading_information', 'black_magic'}
            # Context-aware: allow investigative/reporting texts unless promotion language present
            reporting_ctx = _is_reporting_context(normalized)
            promo_lang = _has_offer_promotion(normalized)
            # Banking notice override — detect legitimate transactional loan/bank messages
            legit_bank_notice = _is_legitimate_banking_notice(normalized, urls)
            if illegal and category in hard_block_cats and confidence >= 0.70:
                if reporting_ctx and not promo_lang:
                    # Treat as contextual mention; do not block
                    blocked = False
                    requires_review = False
                    ai_score = max(ai_score, 55)
                    ai_reasons = list(ai_reasons) + [f"classifier_context:{category}"]
                    policy_hits.append({"category": f"classifier_{category}", "match": "context_reporting"})
                elif category == 'fraud_trade' and legit_bank_notice and not promo_lang:
                    # Transactional banking notice (e.g., loan sanctioned) — ALLOW even with fraud_trade tag
                    # because legitimate banking/loan notifications are NOT fraud
                    blocked = False
                    requires_review = False
                    ai_score = max(ai_score, 35)  # Lower score for legitimate banking
                    ai_reasons = list(ai_reasons) + ["classifier_context:banking_notice"]
                    policy_hits.append({"category": "classifier_fraud_trade", "match": "context_banking_notice", "note": "legitimate_banking_override"})
                    logger.info(f"Banking notice override: blocking disabled. legit_bank_notice={legit_bank_notice}, promo_lang={promo_lang}")
                else:
                    # Genuine fraud
                    blocked = True
                    ai_score = max(ai_score, 88)
                    ai_reasons = list(ai_reasons) + [f"classifier:{category}"]
                    policy_hits.append({"category": f"classifier_{category}", "match": "classifier_confident"})
            elif illegal and category in review_cats and confidence >= 0.60:
                requires_review = True
                ai_score = max(ai_score, 72)
                ai_reasons = list(ai_reasons) + [f"classifier:{category}"]
                policy_hits.append({"category": f"classifier_{category}", "match": "classifier_review"})

    # Compute final decision (0=block, 1=allow), honoring AI-only gate for review
    _ai_only_val = os.environ.get('AI_ONLY_GATE', None)
    if _ai_only_val is None and django_settings is not None:
        # Default to true: treat review as block in send gate
        _ai_only_val = getattr(django_settings, 'AI_ONLY_GATE', 'true')
    ai_only_gate = str(_ai_only_val or '').lower() in {'1', 'true', 'yes'}
    decision_allow = (not blocked) and (not (ai_only_gate and requires_review))

    res = {
        "risk_score": ai_score,
        "blocked": blocked,
        "requires_review": requires_review,
        "reasons": [f"ai:{r}" for r in ai_reasons][:10],
        "urls": urls,
        "policy_hits": policy_hits,
        "decision": 1 if decision_allow else 0,
    }
    if res["blocked"]:
        logger.warning(f"AI-only moderation blocked content. ai_score={ai_score} ai_reasons={ai_reasons}")
    elif res["requires_review"]:
        logger.info(f"AI-only moderation flagged for review. ai_score={ai_score} ai_reasons={ai_reasons}")
    return res


def _ai_evaluate_content(text: str) -> Optional[Dict]:
    """
    AI moderation adapter (OpenAI only).
    Returns {blocked: bool, risk_score: int (0-100), reasons: [str]} or None.
    """
    try:
        return _ai_evaluate_openai(text)
    except Exception as e:
        logger.warning(f"AI moderation adapter error: {e}")
        return None


# ----------------------- Provider Implementations -----------------------

def _ai_evaluate_openai(text: str) -> Optional[Dict]:
    """Call OpenAI Moderations API and map output to our schema."""
    api_key = os.environ.get('OPENAI_API_KEY', None)
    if api_key is None and django_settings is not None:
        api_key = getattr(django_settings, 'OPENAI_API_KEY', None)
    if not api_key:
        return None
    try:
        import requests
        _timeout_val = os.environ.get('AI_TIMEOUT', None)
        if _timeout_val is None and django_settings is not None:
            _timeout_val = getattr(django_settings, 'AI_TIMEOUT', '4')
        timeout = float(str(_timeout_val))
        # Optional retry/backoff (defaults to no retry in app flow)
        _retries_val = os.environ.get('AI_RETRIES', None)
        if _retries_val is None and django_settings is not None:
            _retries_val = getattr(django_settings, 'AI_RETRIES', '0')
        retries = max(0, int(str(_retries_val or '0')))
        _backoff_val = os.environ.get('AI_BACKOFF', None)
        if _backoff_val is None and django_settings is not None:
            _backoff_val = getattr(django_settings, 'AI_BACKOFF', '0.75')
        backoff = float(str(_backoff_val or '0.75'))
        # Use the latest moderation model available
        _model_val = os.environ.get('OPENAI_MODERATION_MODEL', None)
        if _model_val is None and django_settings is not None:
            _model_val = getattr(django_settings, 'OPENAI_MODERATION_MODEL', 'omni-moderation-latest')
        payload = {"model": _model_val or 'omni-moderation-latest', "input": text}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        _project_val = os.environ.get('OPENAI_PROJECT_ID', None)
        if _project_val is None and django_settings is not None:
            _project_val = getattr(django_settings, 'OPENAI_PROJECT_ID', None)
        if _project_val:
            headers["OpenAI-Project"] = _project_val
        _url_val = os.environ.get('OPENAI_MODERATION_URL', None)
        if _url_val is None and django_settings is not None:
            _url_val = getattr(django_settings, 'OPENAI_MODERATION_URL', 'https://api.openai.com/v1/moderations')
        url = _url_val or 'https://api.openai.com/v1/moderations'
        attempts = retries + 1
        for attempt in range(1, attempts + 1):
            logger.info(
                f"OpenAI moderation call attempt {attempt}/{attempts} model={payload.get('model')} "
                f"timeout={timeout} project_header={'yes' if _project_val else 'no'} len={len(text or '')}"
            )
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    results = (data.get('results') or [])
                    if not results:
                        return None
                    res = results[0]
                    flagged = bool(res.get('flagged', False))
                    cat_scores = res.get('category_scores') or {}
                    reasons = [k for k, v in (res.get('categories') or {}).items() if v]
                    # Risk: scale max category score to 0-100
                    max_score = 0.0
                    for v in cat_scores.values():
                        try:
                            max_score = max(max_score, float(v))
                        except Exception:
                            pass
                    risk = int(max_score * 100)
                    logger.info(
                        f"OpenAI moderation ok flagged={flagged} risk={risk} reasons={','.join(reasons[:6])}"
                    )
                    return {"blocked": flagged, "risk_score": risk, "reasons": reasons}
                except Exception:
                    return None
            if resp.status_code == 429 and attempt < attempts:
                retry_after = resp.headers.get('Retry-After')
                wait = float(retry_after) if retry_after else backoff * (2 ** (attempt - 1))
                try:
                    time.sleep(max(0.0, wait))
                except Exception:
                    pass
                logger.warning(
                    f"OpenAI moderation rate limited (429) attempt={attempt} wait={wait} xrid={resp.headers.get('x-request-id','')}"
                )
                continue
            # Log and exit on other errors or final 429
            if not resp.ok:
                try:
                    body = resp.text[:200]
                except Exception:
                    body = ''
                logger.warning(f"OpenAI moderation error: {resp.status_code} {body}")
                return None
        return None
    except Exception as e:
        logger.warning(f"OpenAI moderation request failed: {e}")
        return None


def _ai_illicit_trade_classifier(text: str) -> Optional[Dict]:
    """Optional OpenAI chat-based classifier for policy violations beyond baseline Moderations.

    Returns a dict: {illegal_trade: bool, category: str|None, confidence: float}
    Categories: weapon_trade | drug_trade | fraud_trade | sexual_minors | adult_porn |
                gambling | alcohol | tobacco | misleading_information | unlawful_data |
                illegal_content_or_rights | hate_speech | racism | color_discrimination |
                violence_threat | blackmail_extortion |
                human_trafficking | child_abuse | animal_abuse | gender_based_violence |
                terrorism_extremism | war_promotion |
                money_laundering | black_money | counterfeit_currency | counterfeit_documents |
                hacking_services | doxing_tracking |
                dark_web_illicit_content | banned_content_distribution | black_magic | None
    """
    api_key = os.environ.get('OPENAI_API_KEY', None)
    if api_key is None and django_settings is not None:
        api_key = getattr(django_settings, 'OPENAI_API_KEY', None)
    if not api_key:
        return None
    try:
        import requests
        _timeout_val = os.environ.get('AI_TIMEOUT', None)
        if _timeout_val is None and django_settings is not None:
            _timeout_val = getattr(django_settings, 'AI_TIMEOUT', '4')
        timeout = float(str(_timeout_val))
        _model_val = os.environ.get('OPENAI_CLASSIFIER_MODEL', None)
        if _model_val is None and django_settings is not None:
            _model_val = getattr(django_settings, 'OPENAI_CLASSIFIER_MODEL', 'gpt-4o-mini')
        model = _model_val or 'gpt-4o-mini'
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        _project_val = os.environ.get('OPENAI_PROJECT_ID', None)
        if _project_val is None and django_settings is not None:
            _project_val = getattr(django_settings, 'OPENAI_PROJECT_ID', None)
        if _project_val:
            headers["OpenAI-Project"] = _project_val
        _url_val = os.environ.get('OPENAI_CHAT_URL', None)
        if _url_val is None and django_settings is not None:
            _url_val = getattr(django_settings, 'OPENAI_CHAT_URL', 'https://api.openai.com/v1/chat/completions')
        url = _url_val or 'https://api.openai.com/v1/chat/completions'

        system = (
            "You are a compliance classifier. Return strict JSON only with keys: "
            "illegal_trade (boolean), category (weapon_trade|drug_trade|fraud_trade|sexual_minors|adult_porn|"
            "gambling|alcohol|tobacco|misleading_information|unlawful_data|illegal_content_or_rights|hate_speech|racism|color_discrimination|"
            "violence_threat|blackmail_extortion|human_trafficking|child_abuse|animal_abuse|gender_based_violence|"
            "terrorism_extremism|war_promotion|money_laundering|black_money|counterfeit_currency|counterfeit_documents|"
            "hacking_services|doxing_tracking|dark_web_illicit_content|banned_content_distribution|black_magic|null), "
            "confidence (0-1 float). Classify explicit offer/sale/promotion of illegal goods/services (weapons, drugs, fraud), sexual minors/CSAM, "
            "promotion/distribution of explicit adult pornography or sexual services, gambling/alcohol/tobacco promotion, misleading information campaigns, "
            "unlawful data (leaks, hacking dumps, stolen data), illegal content or rights violations (copyright infringement, CSAM references), "
            "hate speech/harassment targeting protected classes (religion, race, nationality, disability, gender, sexual orientation), explicit threats of violence (kill, murder, killing), "
            "blackmail/extortion (coercion, threats to expose/harm), human trafficking, child abuse, animal abuse/cruelty, gender-based/domestic violence, "
            "terrorism/extremism and war promotion, money laundering/black money, counterfeit currency, fake documents (ID, passport), hacking services (account/email hacking), "
            "doxing/location/IP tracking, and distribution of dark web or government-banned content. Respond only with JSON."
        )
        user = (
            "Text: " + (text or '') + "\n"
            "Respond ONLY with JSON. Example: {\"illegal_trade\": true, \"category\": \"weapon_trade\", \"confidence\": 0.92}"
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 60,
        }
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        if not resp.ok:
            logger.warning(f"OpenAI classifier error: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        content = (((data.get('choices') or [{}])[0]).get('message') or {}).get('content') or ''
        try:
            parsed = json.loads(content)
            illegal = bool(parsed.get('illegal_trade'))
            category = parsed.get('category')
            confidence = float(parsed.get('confidence', 0.0))
            return {"illegal_trade": illegal, "category": category, "confidence": confidence}
        except Exception:
            return None
    except Exception as e:
        logger.warning(f"OpenAI classifier request failed: {e}")
        return None


def _ai_evaluate_gemini(text: str) -> Optional[Dict]:
    """Call Google Gemini generateContent and derive safety ratings."""
    api_key = os.environ.get('GEMINI_API_KEY', None)
    if api_key is None and django_settings is not None:
        api_key = getattr(django_settings, 'GEMINI_API_KEY', None)
    model = os.environ.get('GEMINI_MODEL', None)
    if model is None and django_settings is not None:
        model = getattr(django_settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
    model = model or 'gemini-1.5-flash'
    if not api_key:
        return None
    try:
        import requests
        _timeout_val = os.environ.get('AI_TIMEOUT', None)
        if _timeout_val is None and django_settings is not None:
            _timeout_val = getattr(django_settings, 'AI_TIMEOUT', '4')
        timeout = float(str(_timeout_val))
        _base_val = os.environ.get('GEMINI_GENERATE_URL', None)
        if _base_val is None and django_settings is not None:
            _base_val = getattr(django_settings, 'GEMINI_GENERATE_URL', 'https://generativelanguage.googleapis.com/v1beta')
        url = f"{_base_val or 'https://generativelanguage.googleapis.com/v1beta'}/models/{model}:generateContent?key={api_key}"
        body = {
            "contents": [{"parts": [{"text": text}]}],
            # Encourage safety ratings in candidates
            "generationConfig": {"maxOutputTokens": 64}
        }
        resp = requests.post(url, json=body, timeout=timeout)
        if not resp.ok:
            logger.warning(f"Gemini moderation error: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        candidates = data.get('candidates') or []
        if not candidates:
            return None
        cand = candidates[0]
        safety = cand.get('safetyRatings') or []
        reasons = []
        risk = 0
        blocked = False
        for s in safety:
            cat = s.get('category') or ''
            sev = (s.get('severity') or '').lower()
            # severity might be: 'HARM_BLOCKED', 'HIGH', 'MEDIUM', etc.
            reasons.append(f"gemini:{cat}:{sev}")
            # Map severity to risk buckets
            if 'blocked' in sev:
                blocked = True
                risk = max(risk, 95)
            elif sev in {'high'}:
                risk = max(risk, 85)
            elif sev in {'medium'}:
                risk = max(risk, 70)
            elif sev in {'low'}:
                risk = max(risk, 50)
        return {"blocked": blocked, "risk_score": risk, "reasons": reasons}
    except Exception as e:
        logger.warning(f"Gemini moderation request failed: {e}")
        return None


def _ai_evaluate_anthropic(text: str) -> Optional[Dict]:
    """Use Claude small model to classify moderation categories via JSON prompt."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', None)
    if api_key is None and django_settings is not None:
        api_key = getattr(django_settings, 'ANTHROPIC_API_KEY', None)
    model = os.environ.get('ANTHROPIC_MODEL', None)
    if model is None and django_settings is not None:
        model = getattr(django_settings, 'ANTHROPIC_MODEL', 'claude-3-haiku-20240307')
    model = model or 'claude-3-haiku-20240307'
    if not api_key:
        return None
    try:
        import requests
        _timeout_val = os.environ.get('AI_TIMEOUT', None)
        if _timeout_val is None and django_settings is not None:
            _timeout_val = getattr(django_settings, 'AI_TIMEOUT', '4')
        timeout = float(str(_timeout_val))
        _url_val = os.environ.get('ANTHROPIC_MESSAGES_URL', None)
        if _url_val is None and django_settings is not None:
            _url_val = getattr(django_settings, 'ANTHROPIC_MESSAGES_URL', 'https://api.anthropic.com/v1/messages')
        url = _url_val or 'https://api.anthropic.com/v1/messages'
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        system = (
            "You are a moderation classifier. Return a strict JSON with keys: "
            "blocked (boolean), risk_score (0-100 integer), reasons (array of short strings). "
            "Consider categories adult, sexual minors, violence, drugs, fraud, weapons, extremism, profanity."
        )
        prompt = f"Text: {text}\nRespond only with JSON."
        body = {
            "model": model,
            "max_tokens": 120,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        if not resp.ok:
            logger.warning(f"Anthropic moderation error: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        content = (data.get('content') or [])
        if not content:
            return None
        text_out = content[0].get('text') or content[0].get('content') or ''
        # Attempt to parse JSON response
        try:
            parsed = json.loads(text_out)
            blocked = bool(parsed.get('blocked'))
            score = int(parsed.get('risk_score', 0))
            reasons = parsed.get('reasons') or []
            return {"blocked": blocked, "risk_score": score, "reasons": reasons}
        except Exception:
            # Fallback: coarse mapping
            blocked = 'blocked' in (text_out or '').lower()
            return {"blocked": blocked, "risk_score": 70 if blocked else 40, "reasons": ["anthropic_unparsed"]}
    except Exception as e:
        logger.warning(f"Anthropic moderation request failed: {e}")
        return None


def _ai_evaluate_deepseek(text: str) -> Optional[Dict]:
    """Use DeepSeek chat to classify moderation categories via JSON prompt."""
    api_key = os.environ.get('DEEPSEEK_API_KEY', None)
    if api_key is None and django_settings is not None:
        api_key = getattr(django_settings, 'DEEPSEEK_API_KEY', None)
    model = os.environ.get('DEEPSEEK_MODEL', None)
    if model is None and django_settings is not None:
        model = getattr(django_settings, 'DEEPSEEK_MODEL', 'deepseek-chat')
    model = model or 'deepseek-chat'
    if not api_key:
        return None
    try:
        import requests
        _timeout_val = os.environ.get('AI_TIMEOUT', None)
        if _timeout_val is None and django_settings is not None:
            _timeout_val = getattr(django_settings, 'AI_TIMEOUT', '4')
        timeout = float(str(_timeout_val))
        _url_val = os.environ.get('DEEPSEEK_CHAT_URL', None)
        if _url_val is None and django_settings is not None:
            _url_val = getattr(django_settings, 'DEEPSEEK_CHAT_URL', 'https://api.deepseek.com/chat/completions')
        url = _url_val or 'https://api.deepseek.com/chat/completions'
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        system = (
            "You are a moderation classifier. Return JSON only with keys: blocked (bool), "
            "risk_score (0-100 int), reasons (array)."
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Text: {text}\nRespond only with JSON."}
            ],
            "max_tokens": 120,
            "temperature": 0
        }
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        if not resp.ok:
            logger.warning(f"DeepSeek moderation error: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        out = (((data.get('choices') or [{}])[0]).get('message') or {}).get('content') or ''
        try:
            parsed = json.loads(out)
            blocked = bool(parsed.get('blocked'))
            score = int(parsed.get('risk_score', 0))
            reasons = parsed.get('reasons') or []
            return {"blocked": blocked, "risk_score": score, "reasons": reasons}
        except Exception:
            blocked = 'blocked' in (out or '').lower()
            return {"blocked": blocked, "risk_score": 70 if blocked else 40, "reasons": ["deepseek_unparsed"]}
    except Exception as e:
        logger.warning(f"DeepSeek moderation request failed: {e}")
        return None


# ----------------------- Simple TTL Cache -----------------------

_AI_CACHE: Dict[str, Tuple[Dict, float, int]] = {}
_AI_CACHE_MAX = int(str(
    os.environ.get('AI_CACHE_MAX') if os.environ.get('AI_CACHE_MAX') is not None else (
        getattr(django_settings, 'AI_CACHE_MAX', '500') if django_settings else '500'
    )
))
_AI_CACHE_TTL = int(str(
    os.environ.get('AI_CACHE_TTL') if os.environ.get('AI_CACHE_TTL') is not None else (
        getattr(django_settings, 'AI_CACHE_TTL', '300') if django_settings else '300'
    )
))
_AI_CACHE_SEQ = 0


def _ai_cache_get(key: str) -> Optional[Dict]:
    try:
        entry = _AI_CACHE.get(key)
        if not entry:
            return None
        value, expiry, _seq = entry
        if time.time() > expiry:
            try:
                del _AI_CACHE[key]
            except Exception:
                pass
            return None
        return value
    except Exception:
        return None


def _ai_cache_set(key: str, value: Dict) -> None:
    global _AI_CACHE_SEQ
    try:
        _AI_CACHE_SEQ += 1
        _AI_CACHE[key] = (value, time.time() + _AI_CACHE_TTL, _AI_CACHE_SEQ)
        # Evict oldest when exceeding max
        if len(_AI_CACHE) > _AI_CACHE_MAX:
            # Find oldest by seq
            oldest_key = min(_AI_CACHE.items(), key=lambda kv: kv[1][2])[0]
            try:
                del _AI_CACHE[oldest_key]
            except Exception:
                pass
    except Exception:
        pass
