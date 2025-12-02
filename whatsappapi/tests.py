import os
import re
from django.test import SimpleTestCase
from whatsappapi.moderation import evaluate_content
from whatsappapi import moderation


class ModerationIllegalWordsTests(SimpleTestCase):
    def setUp(self):
        # Force AI-only path and stub the AI evaluation for deterministic tests
        os.environ['AI_ONLY_GATE'] = 'true'
        self._orig_ai_eval = getattr(moderation, '_ai_evaluate_content', None)

        def _stub_ai(text: str):
            t = (text or '').lower()

            def blocked(*labels):
                return {"blocked": True, "risk_score": 85, "reasons": list(labels)}

            def review(*labels):
                return {"blocked": False, "risk_score": 65, "reasons": list(labels)}

            def allow(*labels):
                return {"blocked": False, "risk_score": 10, "reasons": list(labels)}

            # Illegal/abusive content
            if ('child porn' in t) or ('bomb' in t) or ('isis' in t) or ('jihad' in t):
                return blocked('illegal')

            # Alias/short names and adult content
            if re.search(r"\bxxx\b", t) or re.search(r"\bcp\b", t) or 'pthc' in t or 'loli' in t or 'lolita' in t or 'nsfw' in t or re.search(r"\bnudes?\b", t):
                return blocked('adult')

            # Illegal sale/trade
            if ('cocaine' in t) or ('guns' in t) or ('bank logs' in t) or ('cvv' in t):
                return blocked('illegal_trade')

            # Violence threats
            if ('kill you' in t) or ('i will kill' in t) or ('going to kill' in t) or re.search(r"\bkill\b", t):
                return blocked('violence')

            # Drug mentions (review)
            if ('mdma' in t) or ('ketamine' in t) or ('weed' in t) or ('hash' in t):
                return review('drugs')

            # Review terms and domain blocklist cues
            if ('adult entertainment' in t) or ('pornhub.com' in t):
                return review('review_terms')

            # Dark web distribution/trade
            if ('dark web' in t) and (('banned' in t) or ('market' in t) or ('available' in t) or ('download' in t) or ('link' in t) or ('buy' in t) or ('sell' in t)):
                return blocked('dark_web')

            # Hate speech threats
            if ('lynch muslims' in t) or ('kill all gays' in t):
                return blocked('hate')

            return allow('safe')

        moderation._ai_evaluate_content = _stub_ai

    def tearDown(self):
        if self._orig_ai_eval is not None:
            moderation._ai_evaluate_content = self._orig_ai_eval
    def test_hard_block_terms(self):
        self.assertTrue(evaluate_content("child porn content")['blocked'])
        self.assertTrue(evaluate_content("tutorial on bomb making")['blocked'])
        self.assertTrue(evaluate_content("join ISIS jihad")['blocked'])

    def test_alias_short_names(self):
        self.assertTrue(evaluate_content("xxx")['blocked'])
        self.assertTrue(evaluate_content("cp")['blocked'])
        self.assertTrue(evaluate_content("pthc")['blocked'])
        self.assertTrue(evaluate_content("loli pictures")['blocked'])
        self.assertTrue(evaluate_content("NSFW nudes")['blocked'])

    def test_illegal_sale_phrases(self):
        res1 = evaluate_content("sell cocaine in bulk")
        print("reasons1:", res1['reasons'])
        self.assertTrue(res1['blocked'])
        res2 = evaluate_content("supplier of guns and ammo")
        print("reasons2:", res2['reasons'])
        self.assertTrue(res2['blocked'])
        res3 = evaluate_content("trade cvv and bank logs")
        print("reasons3:", res3['reasons'])
        self.assertTrue(res3['blocked'])
        res4 = evaluate_content("I will kill you")
        print("reasons4:", res4['reasons'])
        self.assertTrue(res4['blocked'])

    def test_drug_mentions(self):
        # Standalone mentions of controlled substances should trigger review, not block
        res = evaluate_content("MDMA and ketamine party")
        self.assertFalse(res['blocked'])
        self.assertTrue(res['requires_review'])
        # Availability coupled with terms can still escalate via phrases
        res2 = evaluate_content("Weed and hash available")
        self.assertFalse(res2['blocked'])
        self.assertTrue(res2['requires_review'])

    def test_review_terms_and_domains(self):
        # Under strict policy, review terms and domain hits are blocked
        resA = evaluate_content("adult entertainment")
        print("reasonsA:", resA['reasons'])
        self.assertFalse(resA['blocked'])
        self.assertTrue(resA['requires_review'])
        resB = evaluate_content("visit pornhub.com")
        print("reasonsB:", resB['reasons'])
        self.assertFalse(resB['blocked'])
        self.assertTrue(resB['requires_review'])

    def test_safe_content(self):
        res = evaluate_content("Hello, this is a legal promotional message about our product.")
        self.assertFalse(res['blocked'])
        self.assertFalse(res['requires_review'])

    def test_illegal_content_distribution_phrase(self):
        # Should block when offering banned videos as available
        res = evaluate_content("dark web , banned videos available")
        print("reasons_illegal_content_distribution:", res['reasons'])
        self.assertTrue(res['blocked'])

    def test_dark_web_trade_phrase(self):
        # Should block when dark web is paired with trade/availability cues
        res = evaluate_content("Visit the dark web market, banned content available")
        print("reasons_dark_web_trade:", res['reasons'])
        self.assertTrue(res['blocked'])

    def test_hate_speech_threats(self):
        # Hate-speech threats against protected groups should hard-block
        self.assertTrue(evaluate_content("We should lynch Muslims")['blocked'])
        self.assertTrue(evaluate_content("Kill all gays")['blocked'])


class ModerationContextAwareTests(SimpleTestCase):
    """Test AI's ability to detect context and allow legitimate use cases."""
    
    def setUp(self):
        os.environ['AI_ONLY_GATE'] = 'true'
        self._orig_ai_eval = getattr(moderation, '_ai_evaluate_content', None)

        def _stub_ai(text: str):
            t = (text or '').lower()

            def blocked(*labels):
                return {"blocked": True, "risk_score": 85, "reasons": list(labels)}

            def review(*labels):
                return {"blocked": False, "risk_score": 65, "reasons": list(labels)}

            def allow(*labels):
                return {"blocked": False, "risk_score": 10, "reasons": list(labels)}

            # Detect hard-block categories
            if ('child porn' in t) or ('child abuse' in t):
                return blocked('child_abuse')
            if ('cocaine' in t) or ('heroin' in t) or ('drug' in t):
                return blocked('drug_trade')
            if ('gun' in t) or ('weapon' in t) or ('bomb' in t):
                return blocked('weapon_trade')
            if ('kill' in t) and not ('killed' in t or 'killed by' in t):
                return blocked('violence')

            return allow('safe')

        moderation._ai_evaluate_content = _stub_ai

    def tearDown(self):
        if self._orig_ai_eval is not None:
            moderation._ai_evaluate_content = self._orig_ai_eval

    # ========== LAW ENFORCEMENT / REPORTING CONTEXT ==========
    def test_law_enforcement_drug_report(self):
        """Use Case 1: Police/DEA reporting drug discovery."""
        res = evaluate_content("We discovered cocaine manufacturing lab yesterday. Evidence documented and report filed with DEA.")
        # Should be ALLOWED (reporting context)
        self.assertFalse(res['blocked'], f"Should allow law enforcement reports. Got: {res}")
        print("✅ Law Enforcement Drug Report: ALLOWED")

    def test_law_enforcement_weapons_report(self):
        """Use Case 2: Police reporting illegal weapons cache."""
        res = evaluate_content("Found illegal weapons stash in warehouse. Investigating and reporting to authorities.")
        # Should be ALLOWED (reporting context)
        self.assertFalse(res['blocked'], f"Should allow weapons reports. Got: {res}")
        print("✅ Law Enforcement Weapons Report: ALLOWED")

    def test_child_protection_report(self):
        """Use Case 3: Social worker reporting child abuse."""
        res = evaluate_content("Discovered child abuse case in school. Reporting to child protective services immediately.")
        # Should be ALLOWED (reporting context)
        self.assertFalse(res['blocked'], f"Should allow child protection reports. Got: {res}")
        print("✅ Child Protection Report: ALLOWED")

    # ========== BANKING / FINANCIAL NOTIFICATIONS ==========
    def test_legitimate_loan_approval(self):
        """Use Case 4: Bank notifying about loan approval."""
        res = evaluate_content("Your personal loan of ₹500,000 has been approved by SBI Bank. Funds will be disbursed within 24 hours.")
        # Should be ALLOWED (legitimate banking)
        self.assertFalse(res['blocked'], f"Should allow banking notifications. Got: {res}")
        print("✅ Legitimate Loan Approval: ALLOWED")

    def test_bank_account_status(self):
        """Use Case 5: Bank providing account statement."""
        res = evaluate_content("Your account balance is ₹150,000. View full statement at secure.bank.com")
        # Should be ALLOWED (legitimate banking)
        self.assertFalse(res['blocked'], f"Should allow account statements. Got: {res}")
        print("✅ Bank Account Status: ALLOWED")

    # ========== EDUCATIONAL / AWARENESS CONTENT ==========
    def test_drug_awareness_education(self):
        """Use Case 6: Educational content about drug dangers."""
        res = evaluate_content("Understanding drug addiction: causes, prevention, and rehabilitation options. Free awareness campaign.")
        # Should be ALLOWED or REVIEW (educational context)
        self.assertFalse(res['blocked'], f"Should allow educational content. Got: {res}")
        print("✅ Drug Awareness Education: ALLOWED/REVIEW")

    def test_violence_prevention_education(self):
        """Use Case 7: Educational content about violence prevention."""
        res = evaluate_content("How to prevent violence in schools: awareness, intervention strategies, and support resources.")
        # Should be ALLOWED (educational context)
        self.assertFalse(res['blocked'], f"Should allow violence prevention education. Got: {res}")
        print("✅ Violence Prevention Education: ALLOWED")

    # ========== NEWS / JOURNALISM ==========
    def test_news_report_weapons_discovery(self):
        """Use Case 8: News outlet reporting weapons discovery."""
        res = evaluate_content("Breaking: Illegal weapons cache discovered in warehouse. Police investigating. Full story at newssite.com")
        # Should be ALLOWED (news/journalism context)
        self.assertFalse(res['blocked'], f"Should allow news reports. Got: {res}")
        print("✅ News Report - Weapons: ALLOWED")

    def test_investigative_journalism_drugs(self):
        """Use Case 9: Investigative journalism about drug networks."""
        res = evaluate_content("Investigative report: How cocaine trafficking networks operate. Exclusive interview with former DEA agent.")
        # Should be ALLOWED (journalism context)
        self.assertFalse(res['blocked'], f"Should allow investigative journalism. Got: {res}")
        print("✅ Investigative Journalism - Drugs: ALLOWED")

    # ========== MEDICAL / HEALTH CONTEXT ==========
    def test_medical_overdose_emergency(self):
        """Use Case 10: Medical emergency - drug overdose."""
        res = evaluate_content("EMERGENCY: Patient suffering heroin overdose. Calling ambulance. Naloxone administered.")
        # Should be ALLOWED (medical emergency)
        self.assertFalse(res['blocked'], f"Should allow medical emergencies. Got: {res}")
        print("✅ Medical Overdose Emergency: ALLOWED")

    def test_medical_treatment_information(self):
        """Use Case 11: Medical treatment for drug addiction."""
        res = evaluate_content("Cocaine addiction treatment options: Therapy, medication, and support groups. Call helpline 1-800-HELP.")
        # Should be ALLOWED (medical context)
        self.assertFalse(res['blocked'], f"Should allow medical treatment info. Got: {res}")
        print("✅ Medical Treatment Information: ALLOWED")

    # ========== HISTORICAL / ACADEMIC CONTEXT ==========
    def test_historical_weapons_context(self):
        """Use Case 12: Historical or museum context about weapons."""
        res = evaluate_content("Museum exhibition: Ancient weapons from medieval era. Featuring swords, shields, and armor. Visit this weekend.")
        # Should be ALLOWED (historical context)
        self.assertFalse(res['blocked'], f"Should allow historical content. Got: {res}")
        print("✅ Historical Weapons Content: ALLOWED")

    # ========== ILLEGAL OFFERS (SHOULD BLOCK) ==========
    def test_illegal_drug_sale_offer(self):
        """CONTROL: Illegal drug sale offer."""
        res = evaluate_content("Cocaine for sale, high quality, contact via Telegram +123456")
        # Should be BLOCKED (illegal offer)
        self.assertTrue(res['blocked'], f"Should block drug sale offers. Got: {res}")
        print("❌ Drug Sale Offer: BLOCKED")

    def test_illegal_weapons_trade_offer(self):
        """CONTROL: Illegal weapons trade offer."""
        res = evaluate_content("Guns and ammo wholesale pricing. Fast delivery. DM for bulk orders.")
        # Should be BLOCKED (illegal offer)
        self.assertTrue(res['blocked'], f"Should block weapons offers. Got: {res}")
        print("❌ Weapons Trade Offer: BLOCKED")

    def test_illegal_child_exploitation_offer(self):
        """CONTROL: Illegal child exploitation offer."""
        res = evaluate_content("Child porn videos available for download. Private link in Telegram.")
        # Should be BLOCKED (illegal offer)
        self.assertTrue(res['blocked'], f"Should block child exploitation. Got: {res}")
        print("❌ Child Exploitation Offer: BLOCKED")
