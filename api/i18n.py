"""Alert text, Telugu first.

Visakhapatnam is in Andhra Pradesh, where Telugu is the state language, so it
leads the list and is the default for voice. Hindi and English follow.

CAP carries these as repeated <info> blocks with different <language> values,
so one alert object reaches every speaker without a second message.

REVIEW BEFORE DEPLOYMENT: these strings were written for a prototype and have
not been checked by a native speaker. Alert wording decides whether people
move, and a mistranslated instruction is worse than no alert. Get them read by
someone local before this ever sends to a real number.
"""

from __future__ import annotations

# Ordered: the first is the default for voice and for a single-language SMS.
LANGUAGES = [
    {"code": "te", "cap": "te-IN", "name": "తెలుగు", "english_name": "Telugu"},
    {"code": "hi", "cap": "hi-IN", "name": "हिन्दी", "english_name": "Hindi"},
    {"code": "en", "cap": "en-IN", "name": "English", "english_name": "English"},
]
DEFAULT_LANG = "te"

# {mins} = lead time, {zone} = locality label, {depth} = expected depth in cm
TEMPLATES = {
    "warning": {
        "te": {
            "headline": "వరద హెచ్చరిక",
            "body": "వరద హెచ్చరిక: {zone} ప్రాంతంలో సుమారు {mins} నిమిషాల్లో వరద వచ్చే అవకాశం ఉంది. "
                    "వెంటనే ఎత్తైన సురక్షిత ప్రాంతానికి వెళ్లండి.",
            "instruction": "వరద నీటిలో నడవవద్దు, వాహనం నడపవద్దు. విద్యుత్ ఉపకరణాలను ఆపివేయండి. "
                           "సహాయం కోసం 112కు కాల్ చేయండి.",
        },
        "hi": {
            "headline": "बाढ़ चेतावनी",
            "body": "बाढ़ चेतावनी: {zone} क्षेत्र में लगभग {mins} मिनट में बाढ़ की संभावना है। "
                    "तुरंत ऊँचे और सुरक्षित स्थान पर जाएँ।",
            "instruction": "बाढ़ के पानी में न चलें और न वाहन चलाएँ। बिजली के उपकरण बंद करें। "
                           "सहायता के लिए 112 पर कॉल करें।",
        },
        "en": {
            "headline": "FLOOD WARNING",
            "body": "FLOOD WARNING: flooding expected in {zone} within about {mins} minutes. "
                    "Move to higher ground now.",
            "instruction": "Do not walk or drive through flood water. Switch off electrical "
                           "appliances. Call 112 for help.",
        },
    },
    "watch": {
        "te": {
            "headline": "వరద అప్రమత్తత",
            "body": "వరద అప్రమత్తత: {zone} ప్రాంతంలో {mins} నిమిషాల్లో నీరు పెరిగే అవకాశం ఉంది. "
                    "బయలుదేరడానికి సిద్ధంగా ఉండండి.",
            "instruction": "ముఖ్యమైన వస్తువులు, మందులు సిద్ధం చేసుకోండి. "
                           "సమీప సురక్షిత కేంద్రం ఎక్కడ ఉందో తెలుసుకోండి.",
        },
        "hi": {
            "headline": "बाढ़ की निगरानी",
            "body": "बाढ़ की निगरानी: {zone} क्षेत्र में {mins} मिनट में जलस्तर बढ़ सकता है। "
                    "निकलने के लिए तैयार रहें।",
            "instruction": "ज़रूरी सामान और दवाइयाँ तैयार रखें। निकटतम सुरक्षित केंद्र का पता कर लें।",
        },
        "en": {
            "headline": "FLOOD WATCH",
            "body": "FLOOD WATCH: water may rise in {zone} within {mins} minutes. "
                    "Be ready to leave.",
            "instruction": "Prepare essentials and medicines. Find your nearest shelter now.",
        },
    },
    "advisory": {
        "te": {
            "headline": "వరద సూచన",
            "body": "వరద సూచన: {zone} ప్రాంతంలో నీరు నిలిచే అవకాశం ఉంది. జాగ్రత్తగా ఉండండి.",
            "instruction": "లోతట్టు రోడ్లను తప్పించండి. తాజా సమాచారం కోసం వేచి ఉండండి.",
        },
        "hi": {
            "headline": "बाढ़ सूचना",
            "body": "बाढ़ सूचना: {zone} क्षेत्र में जलभराव हो सकता है। सावधान रहें।",
            "instruction": "निचली सड़कों से बचें। अगली सूचना की प्रतीक्षा करें।",
        },
        "en": {
            "headline": "FLOOD ADVISORY",
            "body": "FLOOD ADVISORY: water may pool in {zone}. Take care.",
            "instruction": "Avoid low-lying roads. Wait for further updates.",
        },
    },
}


def render(severity: str, lang: str, **kw) -> dict:
    tpl = TEMPLATES[severity][lang]
    return {
        "language": lang,
        "headline": tpl["headline"],
        "body": tpl["body"].format(**kw),
        "instruction": tpl["instruction"],
    }


def render_all(severity: str, **kw) -> list[dict]:
    return [render(severity, l["code"], **kw) for l in LANGUAGES]


def sms_text(severity: str, lang: str, **kw) -> str:
    """One SMS. Feature phones may not render Telugu, so ASCII is appended.

    A GSM-7 handset shows Telugu as boxes; sending Unicode also cuts the
    segment limit from 160 to 70 characters. The English line is the fallback
    that always arrives legibly.
    """
    r = render(severity, lang, **kw)
    out = r["body"]                     # the body already opens with the headline
    if lang != "en":
        en = render(severity, "en", **kw)
        out += f" | {en['headline']}"
    return out
