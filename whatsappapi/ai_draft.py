"""
AI Draft Generation Service
Handles OpenAI integration for WhatsApp campaign message generation
"""

import os
import logging
import re
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_ai_draft(prompt, tone='friendly', length='medium', variables=None, campaign_name=''):
    """
    Generate AI-powered campaign message draft using OpenAI
    
    Args:
        prompt (str): User's input prompt
        tone (str): Message tone (friendly, professional, casual, etc.)
        length (str): Message length (short, medium, long)
        variables (list): Available variables for personalization
        campaign_name (str): Campaign name for context
        
    Returns:
        dict: {
            'success': bool,
            'draft': str (if success),
            'error': str (if failed)
        }
    """
    if not prompt:
        return {'success': False, 'error': 'Prompt cannot be empty'}
    
    variables = variables or []
    
    # Get AI provider configuration
    provider = str(getattr(settings, 'AI_PROVIDER', os.environ.get('AI_PROVIDER', 'openai'))).strip().lower()
    
    if provider == 'openai':
        return _generate_with_openai(prompt, tone, length, variables, campaign_name)
    else:
        return {'success': False, 'error': f'Unsupported AI provider: {provider}'}


def _generate_with_openai(prompt, tone, length, variables, campaign_name):
    """
    Generate draft using OpenAI API
    """
    # Get API configuration
    api_key = os.environ.get('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
    if not api_key:
        return {'success': False, 'error': 'OpenAI API key not configured'}
    
    model = os.environ.get('OPENAI_CHAT_MODEL') or getattr(settings, 'OPENAI_CHAT_MODEL', 'gpt-4o-mini')
    timeout = float(str(os.environ.get('AI_TIMEOUT', getattr(settings, 'AI_TIMEOUT', '6'))))
    url = os.environ.get('OPENAI_CHAT_URL') or getattr(settings, 'OPENAI_CHAT_URL', 'https://api.openai.com/v1/chat/completions')
    
    # Build headers
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    project = os.environ.get('OPENAI_PROJECT_ID') or getattr(settings, 'OPENAI_PROJECT_ID', None)
    if project:
        headers['OpenAI-Project'] = project
    
    # Build system and user prompts
    tone_instr = _get_tone_instruction(tone)
    length_instr = _get_length_instruction(length)
    
    system_prompt = _build_system_prompt(tone_instr, length_instr)
    user_prompt = _build_user_prompt(prompt, campaign_name, variables, tone_instr, length_instr)
    
    # Build request body
    body = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ],
        'max_tokens': 320,
        'temperature': 0.5
    }
    
    # Make API request with retries
    try:
        import requests
        import time
        
        attempts = int(str(os.environ.get('AI_RETRIES', getattr(settings, 'AI_RETRIES', '1'))))
        backoff = float(str(os.environ.get('AI_BACKOFF', getattr(settings, 'AI_BACKOFF', '0.75'))))
        
        last_error = None
        draft = None
        
        for i in range(max(1, attempts)):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=timeout)
                
                if resp.status_code == 200:
                    data = resp.json()
                    draft = (((data.get('choices') or [{}])[0]).get('message') or {}).get('content') or ''
                    draft = (draft or '').strip()
                    break
                else:
                    last_error = f"{resp.status_code} {resp.text[:200]}"
                    
            except Exception as e:
                last_error = str(e)
            
            # Wait before retry
            if i < max(1, attempts) - 1:
                time.sleep(backoff * (i + 1))
        
        if not draft:
            return {'success': False, 'error': f'OpenAI request failed: {last_error or "unknown error"}'}
        
        # Log raw AI output
        logger.info(f"RAW AI OUTPUT:\n{draft}\n{'='*50}")
        
        # Clean and structure the draft
        cleaned_draft = clean_and_structure_draft(draft, length, tone)
        
        # Log cleaned output
        logger.info(f"CLEANED OUTPUT:\n{cleaned_draft}\n{'='*50}")
        
        return {
            'success': True,
            'draft': cleaned_draft
        }
        
    except Exception as e:
        logger.error(f"OpenAI request failed: {e}")
        return {'success': False, 'error': f'OpenAI request failed: {str(e)}'}


def _get_tone_instruction(tone):
    """Get tone instruction for the given tone"""
    tone_map = {
        'friendly': 'Use a friendly, conversational tone with a warm greeting and positive phrasing.',
        'professional': 'Use a professional, concise tone. Avoid slang and exclamations; keep structure clear.',
        'casual': 'Use a casual tone with contractions and everyday language. Keep it lightly upbeat.',
        'persuasive': 'Use a persuasive tone: highlight benefits and value, imperative verbs, clear CTA.',
        'informative': 'Use an informative tone: focus on facts and clarity, minimal adjectives, no hype.',
        'urgent': 'Use an urgent tone: time-sensitive wording (today, now), short sentences, remain polite.',
        'formal': 'Use a formal tone: no contractions, polite salutations, conservative punctuation.',
        'playful': 'Use a playful tone: light humor and upbeat wording. Keep jokes tasteful and minimal.',
        'empathetic': 'Use an empathetic tone: acknowledge user feelings and offer help (we understand, happy to help).',
        'authoritative': 'Use an authoritative tone: assertive and confident, avoid hedging, state benefits directly.',
        'humorous': 'Use a humorous tone: include one mild, tasteful pun or light joke; keep it subtle.',
        'storytelling': 'Use a storytelling tone: open with a brief scenario or mini story before the offer.',
        'promotional': 'Use a promotional tone: highlight offers, savings, and incentives; include a clear CTA.',
        'neutral': 'Use a neutral tone: objective and factual; avoid hype or strong emotion.',
        'creative': 'Use a creative tone: vivid, metaphorical phrasing while keeping the message clear.'
    }
    return tone_map.get(tone, tone_map['friendly'])


def _get_length_instruction(length):
    """Get length instruction for the given length"""
    length_map = {
        'short': 'Keep it short: 2–3 lines.',
        'medium': 'Keep it medium: 4–6 lines.',
        'long': 'Allow longer: 7–10 lines.'
    }
    return length_map.get(length, length_map['medium'])


def _build_system_prompt(tone_instr, length_instr):
    """Build the system prompt for OpenAI - Intelligent Agent Version"""
    return (
        "You are an expert WhatsApp marketing copywriter and AI agent. Your mission is to create "
        "compelling, persuasive marketing messages that drive customer action.\n\n"
        
        "YOUR CAPABILITIES:\n"
        "- Understand ANY business type (retail, healthcare, education, tech, real estate, travel, etc.)\n"
        "- Analyze user's business, offer, and target audience intelligently\n"
        "- Create engaging, personalized marketing content from scratch\n"
        "- Adapt writing style dynamically to match requested tone and length\n"
        "- Extract and highlight key information (dates, prices, locations, URLs)\n"
        "- Generate industry-appropriate language and benefits\n"
        "- Add strategic emojis and WhatsApp formatting\n\n"
        
        "CONTENT STRUCTURE:\n"
        "1. *Header*: Eye-catching title with emoji OUTSIDE bold (e.g., 🛒 *Sale Alert!*)\n"
        "2. *Greeting*: Emoji BEFORE asterisk, name inside (e.g., 📢 *Exciting News, {first_name}!*)\n"
        "   NEVER put emoji inside *bold* markers - emoji must be OUTSIDE\n"
        "3. *Hook*: Compelling opening line that grabs attention\n"
        "4. *Key Details*: If provided - dates (📅), times (⏰), prices (💰), locations (📍)\n"
        "   Format: Each on separate line with emoji prefix\n"
        "5. *Benefits Section*: Use clear header like *Why Choose Us?* or *What's Included:*\n"
        "   Then list 3-4 bullet points with ✅ emoji (NOT hyphens!)\n"
        "   Format: ✅ Benefit description (clear and concise)\n"
        "6. *Description*: Short engaging paragraph (2-3 sentences max)\n"
        "7. *CTA*: Strong call-to-action\n"
        "   If URL provided: Put URL on its own line (no markdown brackets)\n"
        "   Example: 👉 *Download now:*\n   https://example.com\n"
        "8. *Closing*: Warm sign-off (e.g., Looking forward to seeing you! 🎉)\n\n"
        
        "FORMATTING RULES (CRITICAL):\n"
        "- Use SINGLE asterisk *bold* for emphasis - NEVER use double **bold**\n"
        "- NEVER put emojis INSIDE *bold* - put emoji BEFORE the asterisk\n"
        "   WRONG: *📢 News!* or *🛒 *Title**\n"
        "   CORRECT: 📢 *News!* or 🛒 *Title*\n"
        "- WhatsApp ONLY supports: *bold*, _italic_, ~strikethrough~\n"
        "- NEVER use markdown format like **bold** or [text](url)\n"
        "- For URLs: Put URL on its own line, no brackets\n"
        "- Bullet points: ✅ must be followed by text on SAME line\n"
        "   CORRECT: ✅ Benefit text here\n"
        "   WRONG: ✅ (newline) Benefit text\n"
        "- Add blank lines between sections for readability\n"
        "- Use 3-5 emojis strategically (not too many!)\n"
        "- Keep paragraphs short (2-3 sentences max)\n"
        "- Always include {first_name} for personalization\n\n"
        
        f"TONE & LENGTH REQUIREMENTS:\n"
        f"- Tone: {tone_instr}\n"
        f"- Length: {length_instr}\n"
        f"- Follow these constraints strictly and naturally\n\n"
        
        "BUSINESS INTELLIGENCE:\n"
        "- Detect business type from context clues\n"
        "- Use industry-specific terminology appropriately\n"
        "- Highlight benefits relevant to that industry\n"
        "- Create urgency when appropriate (limited time, exclusive offer, etc.)\n"
        "- Adapt language to target audience\n\n"
        
        "QUALITY STANDARDS:\n"
        "- Be concise but impactful\n"
        "- Avoid spam-like or overly salesy language\n"
        "- Keep within WhatsApp limits (max 4000 characters)\n"
        "- Make every word count\n"
        "- Focus on customer benefits, not just features\n\n"
        
        "OUTPUT: Generate a complete, ready-to-send WhatsApp marketing message that drives action."
    )


def _build_user_prompt(prompt, campaign_name, variables, tone_instr, length_instr):
    """Build the user prompt for OpenAI - Improved Version"""
    var_text = ', '.join(variables) or 'first_name'
    first_var = var_text.split(',')[0].strip() if variables else 'first_name'
    
    return (
        f"CAMPAIGN NAME: {campaign_name or 'Marketing Campaign'}\n\n"
        
        f"PERSONALIZATION VARIABLES AVAILABLE:\n"
        f"- {var_text}\n"
        f"- Use {{{first_var}}} in the greeting for personalization\n\n"
        
        f"USER'S BUSINESS/OFFER DESCRIPTION:\n"
        f"\"\"\"\n{prompt}\n\"\"\"\n\n"
        
        f"YOUR TASK:\n"
        f"Create a compelling WhatsApp marketing message based on the above description.\n\n"
        
        f"REQUIREMENTS:\n"
        f"- Tone: {tone_instr}\n"
        f"- Length: {length_instr}\n"
        f"- Include {{{first_var}}} for personalization\n"
        f"- Extract any dates, times, prices, locations, or URLs from the description\n"
        f"- Create engaging, action-driving content\n"
        f"- Add appropriate emojis and WhatsApp formatting\n"
        f"- Make it ready to send immediately\n\n"
        
        f"Generate the complete message now:"
    )


def clean_and_structure_draft(draft, length='medium', tone='friendly'):
    """
    Light cleanup of AI-generated draft - Preserve AI creativity!
    
    Since we now have an intelligent AI agent, this function only does minimal cleanup
    to ensure quality and consistency, while preserving the AI's creative output.
    
    Args:
        draft (str): Raw AI-generated draft from intelligent agent
        length (str): Desired length (for validation only)
        tone (str): Desired tone (for validation only)
        
    Returns:
        str: Lightly cleaned draft with AI creativity preserved
    """
    if not draft:
        return draft
    
    import logging
    import re
    logger = logging.getLogger(__name__)
    
    # Step 1: Basic cleanup - trim whitespace
    output = draft.strip()
    
    # Step 1b: Convert markdown to WhatsApp format (CRITICAL)
    # Convert **bold** (markdown) to *bold* (WhatsApp)
    output = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', output)
    # Convert [text](url) markdown links to just URL on new line
    output = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\2', output)
    # Remove any remaining markdown link syntax
    output = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\2', output)
    
    # Step 1c: Fix emoji inside bold patterns (CRITICAL)
    # Fix patterns like *🛒 *Title* or *📢 *News*, {name}!*
    # Move emoji outside the bold markers
    emoji_pattern = r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF]'
    # Fix: *emoji *text* → emoji *text*
    output = re.sub(r'\*(' + emoji_pattern + r'+)\s*\*([^*]+)\*', r'\1 *\2*', output)
    # Fix: *emoji text* where emoji should be outside
    output = re.sub(r'\*(' + emoji_pattern + r')\s+([^*]+)\*', r'\1 *\2*', output)
    
    # Step 1d: Fix ✅ bullet points separated from text
    # If ✅ is on its own line, join with next line
    output = re.sub(r'✅\s*\n+([A-Z])', r'✅ \1', output)
    output = re.sub(r'✅\s*\n+([a-z])', r'✅ \1', output)
    
    # Step 2: Ensure proper paragraph spacing (max double newlines)
    output = re.sub(r'\n{3,}', '\n\n', output)
    
    # Step 3: Ensure personalization variable exists
    if '{first_name}' not in output.lower():
        # Try to add it to the first greeting line
        if 'hi ' in output.lower():
            output = re.sub(r'\bhi\b', 'Hi {first_name}', output, count=1, flags=re.IGNORECASE)
        elif 'hello' in output.lower():
            output = re.sub(r'\bhello\b', 'Hello {first_name}', output, count=1, flags=re.IGNORECASE)
        elif 'hey' in output.lower():
            output = re.sub(r'\bhey\b', 'Hey {first_name}', output, count=1, flags=re.IGNORECASE)
        elif 'dear' in output.lower():
            output = re.sub(r'\bdear\b', 'Dear {first_name}', output, count=1, flags=re.IGNORECASE)
    
    # Step 4: Quality checks (log warnings, don't modify)
    emoji_count = len(re.findall(r'[😀-🙏🎀-🗿🚀-🛸💀-💿]', output))
    if emoji_count > 10:
        logger.warning(f"AI generated {emoji_count} emojis (recommended: 3-5)")
    
    char_count = len(output)
    if char_count > 4000:
        logger.warning(f"AI generated {char_count} characters (WhatsApp limit: 4096)")
    
    # Step 5: Ensure proper spacing before URLs and closing
    # Add blank line before URLs if missing
    output = re.sub(r'([^\n])\n(\*[^*]+\*:\s*https?://)', r'\1\n\n\2', output)
    
    # Step 6: Fix hyphen bullet points (replace with ✅)
    # Match lines starting with hyphen and space
    output = re.sub(r'\n-\s+([A-Z])', r'\n✅ \1', output)  # Start of sentence
    output = re.sub(r'\n-([A-Z])', r'\n✅ \1', output)     # No space after hyphen
    
    # Step 6b: Ensure proper line breaks for bullet points
    # Fix ✅ bullets running together - ensure each ✅ is on its own line
    output = re.sub(r'([^\n])✅', r'\1\n✅', output)  # Add newline before ✅ if missing
    # Remove trailing spaces from lines (markdown line breaks don't work in WhatsApp)
    output = re.sub(r'  +\n', r'\n', output)
    
    # Step 7: Clean up URL formatting
    # Remove brackets around URLs if present
    output = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'\2', output)
    
    # Step 8: Fix missing spaces in text (common AI error)
    # Fix "AEDinstead" → "AED instead"
    output = re.sub(r'AED([a-z])', r'AED \1', output)
    # Fix "AED!" → "AED! " (space after punctuation before capital letter)
    output = re.sub(r'AED!([A-Z])', r'AED!\n\n\1', output)
    # Fix "999 AED!Why" → "999 AED!\n\nWhy"
    output = re.sub(r'([!.?])([A-Z][a-z]+\s+[A-Z])', r'\1\n\n\2', output)
    # Fix "offon" → "off on" (common AI spacing error)
    output = re.sub(r'\boffon\b', 'off on', output, flags=re.IGNORECASE)
    # Fix "% off" spacing issues
    output = re.sub(r'(\d+%)\s*off\s*on', r'\1 off on', output)
    # Fix "at" spacing issues (e.g., "atABC" → "at ABC")
    output = re.sub(r'\bat([A-Z])', r'at \1', output)
    # Fix "on" followed by capital letter without space
    output = re.sub(r'\bon([A-Z])', r'on \1', output)
    
    # Step 9: Ensure blank line before section headers
    # Add blank line before "Why Choose Us?" or similar headers
    output = re.sub(r'([!.?])\n(\*[^*]+\*:\s*✅)', r'\1\n\n\2', output)  # Before bold header with emoji
    output = re.sub(r'([!.?])([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+\?)', r'\1\n\n\2', output)  # Before "Why Choose Us?"
    
    # Step 10: Ensure "Why Choose Us?" is bold and has proper spacing
    if 'Why Choose Us?' in output and '*Why Choose Us?*' not in output:
        output = output.replace('Why Choose Us?', '*Why Choose Us?*')
    if 'What\'s Included:' in output and '*What\'s Included:*' not in output:
        output = output.replace('What\'s Included:', '*What\'s Included:*')
    if 'Why Download?' in output and '*Why Download?*' not in output:
        output = output.replace('Why Download?', '*Why Download?*')
    
    # Step 11: Ensure blank line after section headers before bullets
    output = re.sub(r'(\*[^*]+\*\?)\n(✅)', r'\1\n\n\2', output)  # After "Why...?" before ✅
    
    # Step 12: Ensure greeting has emoji
    if 'Exciting News' in output and '📢' not in output[:100]:
        output = output.replace('Exciting News', '📢 *Exciting News*', 1)
    
    # Step 9: Return AI-generated content with minimal changes
    logger.info(f"Draft cleanup complete. Length: {char_count} chars, Emojis: {emoji_count}")
    
    return output


# REMOVED: Heavy reconstruction logic (lines 283-438 in old version)
# The intelligent AI agent now handles:
# - Business type detection
# - Header creation
# - Greeting generation
# - Data extraction and formatting
# - Feature listing
# - Paragraph writing
# - CTA and closing
# We only do light cleanup above to ensure quality!


def generate_marketing_guide(draft, tone, campaign_name):
    """
    Generate marketing tips based on draft analysis
    Moved from views.py for better organization
    
    Args:
        draft (str): The generated draft text
        tone (str): Message tone (friendly, professional, etc.)
        campaign_name (str): Campaign name for context
        
    Returns:
        dict: Marketing guide with structure tips, emoji advice, and common mistakes
    """
    import re
    
    # Tone-specific emoji mappings
    emoji_map = {
        'friendly': {'greeting': '👋😊', 'benefit': '✨', 'cta': '→', 'end': '💕'},
        'professional': {'greeting': '👋', 'benefit': '✓', 'cta': '→', 'end': '✅'},
        'casual': {'greeting': '👋😎', 'benefit': '🔥', 'cta': '→', 'end': '😄'},
        'persuasive': {'greeting': '💎', 'benefit': '⭐', 'cta': '🚀', 'end': '✨'},
        'urgent': {'greeting': '⚠️', 'benefit': '⏰', 'cta': '🚀', 'end': '➡️'},
        'promotional': {'greeting': '🎁', 'benefit': '💰', 'cta': '🛒', 'end': '🎉'},
    }
    
    default_emojis = emoji_map.get(tone, emoji_map['friendly'])
    
    # Analyze draft content
    has_personalization = '{' in draft and '}' in draft
    has_cta = any(word in draft.lower() for word in ['click', 'call', 'visit', 'reply', 'contact', 'get', 'buy', 'join', 'download'])
    has_urgency = any(word in draft.lower() for word in ['today', 'now', 'limited', 'urgent', 'asap', 'hurry', 'quick'])
    emoji_count = len(re.findall(r'[😀-🙏🎀-🗿🚀-🛸💀-💿]', draft))
    line_count = len(draft.split('\n'))
    
    # Generate dynamic structure recommendations
    structure = [
        f"{'✓' if has_personalization else '⚠️'} Personalization: Use {{first_name}} early (currently {'present' if has_personalization else 'missing'})",
        "🎯 Hook: Start with benefit, not info",
        "📢 Body: Keep 4-6 lines, use bullets",
        f"{'✓' if has_cta else '⚠️'} CTA: End with action (currently {'present' if has_cta else 'missing'})",
        f"{'✓' if has_urgency else '—'} Urgency: Add if needed (currently {'present' if has_urgency else 'optional'})"
    ]
    
    # Generate emoji placement tips
    emoji_tips = [
        f"🎯 Greeting: {default_emojis.get('greeting', '👋')} Use at start only",
        f"✨ Highlights: {default_emojis.get('benefit', '💡')} Use 2-3 for key points",
        f"🚀 Action: {default_emojis.get('cta', '→')} Place before CTA",
        f"🎉 Closing: {default_emojis.get('end', '👍')} End message warmly"
    ]
    
    # Tone-specific advice
    tone_advice = {
        'friendly': 'Use 1-2 emojis max - warmth comes from words, not symbols',
        'professional': 'Minimal emojis (only for structure). Use ✓ for lists',
        'casual': '2-4 emojis OK. Use trending ones like 🔥💯',
        'persuasive': 'Benefit emojis (💎 premium, 🚀 speed, ⭐ quality)',
        'urgent': 'Action emojis (⏰ time, 🚀 go) show immediacy',
        'promotional': '1 emoji per line max. Focus on 💰💳🎁'
    }
    
    # Generate common mistakes (dynamic based on draft)
    common_mistakes = [
        f"{'⚠️' if emoji_count > 10 else '—'} Too many emojis ({emoji_count} found - keep under 5)",
        "❌ Emojis AFTER words (place BEFORE action)",
        f"{'⚠️' if not has_cta else '✓'} Missing CTA (message needs clear action)",
        f"{'⚠️' if not has_personalization else '✓'} No personalization (adds 20x more engagement)",
        f"{'⚠️' if line_count > 10 else '—'} Walls of text ({line_count} lines - keep 4-6)"
    ]
    
    guide = {
        'structure': structure,
        'emoji_tips': emoji_tips,
        'tone_advice': tone_advice.get(tone, tone_advice['friendly']),
        'common_mistakes': common_mistakes
    }
    
    return guide
