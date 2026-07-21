"""
Reference photo presets for the AI Photoshoot platform.
Production-quality presets with identity-preserving prompts.

Seeds placeholder reference_photos for local development and production.
Each preset includes detailed technical photography parameters and identity-preserving prompts.

Run: python -m app.seed
"""
import hashlib
import io
import logging
import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, check_db_connection, engine
from app.models.reference_photo import ReferencePhoto
from app.models.user import User
from app.services import storage
from app.services.auth import hash_password

logger = logging.getLogger(__name__)

PLACEHOLDER_PRESETS = [
    {
        "title": "Luxury Hotel Lobby",
        "collection": "Luxury",
        "color": (176, 144, 96),
        "style_description": {
            "camera_angle": "eye level, slightly elevated",
            "lens": "85mm, focal length creates flattering proportions",
            "shot_type": "medium portrait, full body to waist",
            "lighting": "soft directional light from 45° left, warm 3200K tungsten",
            "background": "premium marble lobby with geometric patterns, bokeh 2.5m away",
            "pose": "standing with weight on back leg, subtle shoulder angle",
            "expression": "calm confident smile, eyes engaging camera",
            "hairstyle": "match user reference exactly, well-groomed",
            "outfit": "luxury formal wear: tailored blazer, silk shirt, designer accessories",
            "depth_of_field": "shallow f/1.4, background creamy blur",
            "color_grade": "warm premium tones, lifted shadows, saturated jewel tones",
            "mood": "luxurious, confident, professional elegance",
        },
        "prompt_template": """You are a professional luxury portrait photographer. 
You receive TWO reference images:

PRIMARY REFERENCE (User's Face)
Extract and preserve ONLY:
- Facial identity and unique features
- Skin tone and texture
- Eye color and expression
- Nose shape and proportions
- Lip color and shape
- Jawline and face shape
- Age and natural features
- Hairline and hair color

STYLE REFERENCE (Photography Style)
Extract ONLY:
- Pose: standing with subtle weight shift, relaxed shoulders
- Hairstyle: match user's natural hair exactly
- Expression: confident, subtle smile, engaged eyes
- Outfit: luxury formal wear (tailored blazer, silk shirt, designer accessories)
- Lighting: soft directional 45° left, warm 3200K tungsten
- Background: premium marble lobby with geometric patterns
- Camera angle: eye level, slightly elevated 85mm lens perspective
- Depth of field: shallow f/1.4, creamy background bokeh
- Color grade: warm premium tones, lifted shadows, saturated jewels
- Composition: medium portrait framing, full body to waist

CRITICAL RULES:
1. The user's FACE must be 100% recognizable as themselves
2. Copy ONLY pose, outfit, lighting, background from style reference
3. Never blend two different faces together
4. Maintain facial proportions and unique characteristics
5. Make it look like the user naturally attended this luxury photoshoot

TECHNICAL REQUIREMENTS:
- Professional photoshoot quality
- 85mm focal length flattery
- Shallow depth of field bokeh
- Warm premium color grading
- Sharp focus on face and eyes
- Professional lighting technique
- High-end fashion photography standard
- 8K resolution quality
- No artifacts or distortions

Generate the final composite: User's face + luxury hotel photoshoot styling.""",
    },
    {
        "title": "Old Money Estate",
        "collection": "Old Money",
        "color": (96, 120, 108),
        "style_description": {
            "camera_angle": "slightly above eye level",
            "lens": "50mm, timeless portrait lens",
            "shot_type": "medium portrait with context",
            "lighting": "golden diffused window light from left, natural 4000K",
            "background": "classical estate library or drawing room, antique furniture",
            "pose": "seated on vintage furniture, relaxed elegance",
            "expression": "subtle refined smile, poised composure",
            "hairstyle": "polished classic style, well-maintained",
            "outfit": "understated luxury: cashmere, pearls, vintage Hermès bag",
            "depth_of_field": "soft medium bokeh f/2.8",
            "color_grade": "muted palette, refined earthy tones, film-like quality",
            "mood": "timeless elegance, generational wealth, understated luxury",
        },
        "prompt_template": """You are a heritage portrait photographer specializing in generational wealth portraiture.

PRIMARY REFERENCE (User's Identity)
Preserve exclusively:
- Facial identity and character
- Skin tone and natural beauty
- Eye color and depth
- Facial proportions and structure
- Age and wisdom lines
- Natural hair color and texture
- Unique personal features

STYLE REFERENCE (Old Money Aesthetic)
Extract exclusively:
- Pose: seated with perfect posture, timeless elegance
- Hairstyle: polished classic style, heritage elegance
- Expression: subtle refined smile, composed poise
- Outfit: understated luxury (cashmere, pearls, vintage accessories)
- Lighting: golden diffused window light 45°, warm natural 4000K
- Background: classical estate library, antique mahogany, period furniture
- Camera: 50mm lens, 1.3m distance for timeless proportions
- Depth of field: soft medium bokeh f/2.8, painterly quality
- Color grade: muted earthy palette, warm neutrals, film-like quality
- Composition: seated in period setting, heritage aesthetic

IDENTITY PRESERVATION RULES:
1. User's face must be unmistakably recognizable as themselves
2. Copy ONLY estate styling, pose, outfit, lighting
3. Never merge identities
4. Maintain natural aging and character lines
5. Create the illusion user belongs in old money setting

TECHNICAL REQUIREMENTS:
- Heritage photography aesthetic
- 50mm lens natural proportions
- Warm 4000K natural window lighting
- Soft film-like color science
- Medium depth of field with painterly quality
- Classical composition and framing
- Museum-quality portraiture standard
- Timeless aesthetic, not trendy
- Professional retouching, natural enhancement

Produce: User's face in old money estate photoshoot context.""",
    },
    {
        "title": "Editorial High Fashion",
        "collection": "Editorial",
        "color": (64, 64, 80),
        "style_description": {
            "camera_angle": "direct frontal, powerful gaze",
            "lens": "70mm, editorial flattery",
            "shot_type": "close-up portrait, face-focused",
            "lighting": "dramatic directional key light, minimal fill",
            "background": "seamless neutral or artistic abstract backdrop",
            "pose": "direct camera engagement, strong posture",
            "expression": "intense focused gaze, editorial intensity",
            "hairstyle": "styled and sculpted, editorial perfection",
            "outfit": "haute couture or designer piece, high fashion",
            "depth_of_field": "sharp focus face, f/4.0",
            "color_grade": "high contrast, editorial color grading, saturated",
            "mood": "powerful, editorial, high fashion confidence",
        },
        "prompt_template": """You are an editorial fashion photographer for Vogue-level publications.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and character
- Unique facial proportions
- Skin tone and texture
- Eye color and intensity
- Nose and lip geometry
- Cheekbones and face shape
- Natural beauty markers
- Age and authenticity

STYLE REFERENCE (Editorial High Fashion)
Extract exclusively:
- Pose: direct camera engagement, powerful posture
- Expression: intense focused gaze, editorial intensity
- Hairstyle: styled to editorial perfection
- Outfit: haute couture or prestige designer piece
- Lighting: dramatic directional key light, 3:1 ratio
- Background: seamless neutral or artistic abstract
- Camera: 70mm lens, editorial flattery distance
- Depth of field: sharp face focus f/4.0, editorial sharpness
- Color grade: high contrast, saturated color, editorial treatment
- Composition: close-up face-focused editorial framing

CRITICAL FACE PRESERVATION:
1. User's face must be 100% recognizable and authentic
2. Editorial styling applied to user's actual face
3. No face merging or identity blending
4. Maintain facial uniqueness and character
5. Make it appear user is featured in editorial shoot

TECHNICAL SPECIFICATIONS:
- Editorial photography standard
- 70mm lens flattery
- Dramatic 3:1 lighting ratio
- Sharp focus on facial features
- High contrast color grading
- Magazine cover quality
- Professional makeup enhancement
- Sharply detailed, editorial crispness
- Vogue or Harper's Bazaar aesthetic

Generate: User's striking editorial fashion portrait.""",
    },
    {
        "title": "Street Fashion Urban",
        "collection": "Street Fashion",
        "color": (104, 104, 120),
        "style_description": {
            "camera_angle": "natural eye level, candid feel",
            "lens": "35mm, environmental portrait",
            "shot_type": "three-quarter body with environment",
            "lighting": "natural daylight, directional city light",
            "background": "urban street, architecture, graffiti, city texture",
            "pose": "natural stance, walking or pause, relaxed confidence",
            "expression": "natural, candid, street style attitude",
            "hairstyle": "match user's style, street-appropriate",
            "outfit": "current trendy streetwear, personal style expression",
            "depth_of_field": "environmental context f/5.6",
            "color_grade": "vibrant urban palette, modern color science",
            "mood": "effortless cool, urban confidence, street authenticity",
        },
        "prompt_template": """You are a street style photographer capturing authentic urban culture.

PRIMARY REFERENCE (User's Identity)
Preserve exclusively:
- Facial identity and personal character
- Skin tone and natural features
- Eye color and expression
- Facial structure and age
- Hair color and natural texture
- Unique personal markers
- Authentic appearance

STYLE REFERENCE (Street Fashion Urban)
Extract exclusively:
- Pose: natural walking stance, urban confidence
- Expression: authentic candid moment
- Hairstyle: match user's natural style exactly
- Outfit: trendy streetwear, personal style (current fashion)
- Lighting: natural daylight, directional city light
- Background: urban street environment, architecture, texture
- Camera: 35mm lens, environmental storytelling
- Depth of field: f/5.6 showing context and subject
- Color grade: vibrant urban palette, modern street aesthetic
- Composition: three-quarter body, street style framing

IDENTITY PRESERVATION MANDATE:
1. User's face unmistakably recognizable and authentic
2. Street style applied to user's actual appearance
3. Never blend two different faces
4. Maintain personal style and character
5. Look like genuine street style photography of user

TECHNICAL REQUIREMENTS:
- Street photography authenticity
- 35mm lens environmental context
- Natural daylight urban lighting
- Sharp depth of field f/5.6
- Vibrant natural color palette
- Fashion editorial street quality
- Authentic candid feeling
- Current trends integrated naturally
- Professional street style standard

Produce: User's authentic street fashion moment.""",
    },
    {
        "title": "Korean Beauty Standard",
        "collection": "Korean",
        "color": (192, 160, 176),
        "style_description": {
            "camera_angle": "slightly below eye level, flattering",
            "lens": "50mm, beauty standard lens",
            "shot_type": "close face portrait, beauty focus",
            "lighting": "soft diffused front lighting, butterfly pattern",
            "background": "soft pastel gradient or minimalist aesthetic",
            "pose": "gentle tilt, serene beauty pose",
            "expression": "soft serene gaze, gentle elegance",
            "hairstyle": "styled for Korean beauty aesthetic",
            "outfit": "soft elegant clothing, pastel tones",
            "depth_of_field": "soft ethereal bokeh f/1.8",
            "color_grade": "soft pink undertones, luminous skin, beauty filter effect",
            "mood": "serene beauty, Korean glamour, elegant femininity",
        },
        "prompt_template": """You are a Korean beauty and glamour photographer specializing in ethereal portraiture.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and unique beauty
- Skin tone and texture
- Eye shape and color
- Nose and lip geometry
- Face shape and proportions
- Age and natural features
- Personal distinctive markers

STYLE REFERENCE (Korean Beauty Standard)
Extract exclusively:
- Pose: gentle tilt, serene beauty pose
- Expression: soft serene gaze, gentle elegance
- Hairstyle: styled for Korean beauty aesthetic
- Outfit: soft elegant pastels, minimalist luxury
- Lighting: soft diffused butterfly pattern, 5200K
- Background: soft pastel gradient, minimalist aesthetic
- Camera: 50mm lens, beauty standard distance
- Depth of field: ethereal soft bokeh f/1.8
- Color grade: soft pink undertones, luminous skin, beauty enhancement
- Composition: close face portrait, beauty photography focus

FACE AUTHENTICITY REQUIREMENT:
1. User's face must be recognizable as themselves
2. Korean beauty styling applied to user's face
3. Never merge two different faces
4. Enhance natural beauty, don't replace identity
5. Authentic user appearing in Korean beauty photoshoot

TECHNICAL SPECIFICATIONS:
- Korean beauty photography standard
- 50mm lens flattery distance
- Soft diffused butterfly lighting
- Ethereal depth of field f/1.8
- Luminous skin enhancement
- Soft pink color grading
- Beauty retouching excellence
- Serene elegant aesthetic
- Contemporary Korean glamour standard

Generate: User's ethereal Korean beauty portrait.""",
    },
    {
        "title": "Business Professional",
        "collection": "Business",
        "color": (112, 112, 128),
        "style_description": {
            "camera_angle": "eye level, confident posture",
            "lens": "85mm, professional flattery",
            "shot_type": "headshot to shoulders",
            "lighting": "even professional studio lighting, 5600K",
            "background": "neutral blurred corporate backdrop",
            "pose": "upright confident posture, direct camera",
            "expression": "professional warmth, trustworthy composure",
            "hairstyle": "professional groomed style",
            "outfit": "business formal: blazer, dress shirt, professional accessories",
            "depth_of_field": "focused face, subtle background blur f/4.0",
            "color_grade": "professional neutral, natural skin tones",
            "mood": "professional credibility, business confidence, trustworthy",
        },
        "prompt_template": """You are a corporate and LinkedIn professional photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and professional appearance
- Skin tone and natural features
- Eye color and trustworthy expression
- Face shape and proportions
- Age and professional character
- Natural unique features
- Authentic appearance

STYLE REFERENCE (Business Professional)
Extract exclusively:
- Pose: upright confident professional posture
- Expression: warm professional composure, trustworthy
- Hairstyle: professional groomed style, business appropriate
- Outfit: business formal (blazer, dress shirt, accessories)
- Lighting: even professional studio 5600K, balanced
- Background: neutral blurred corporate backdrop
- Camera: 85mm lens, professional headshot distance
- Depth of field: focused face, professional blur f/4.0
- Color grade: professional neutral, natural skin enhancement
- Composition: headshot to shoulders, LinkedIn standard

PROFESSIONAL AUTHENTICITY:
1. User's face unmistakably professional and recognizable
2. Business styling applied to user's actual appearance
3. No identity blending or face merging
4. Enhance professionalism, maintain authenticity
5. Corporate credibility and business trustworthiness

TECHNICAL REQUIREMENTS:
- Professional headshot standard
- 85mm lens professional flattery
- Even studio lighting 5600K
- Sharp focus face f/4.0
- Natural professional color grading
- Corporate photography quality
- LinkedIn profile excellence
- Business credibility aesthetic
- Executive portrait standard

Generate: User's professional business headshot.""",
    },
    {
        "title": "Graduation Ceremony",
        "collection": "Graduation",
        "color": (160, 120, 80),
        "style_description": {
            "camera_angle": "eye level, celebratory",
            "lens": "50mm, milestone lens",
            "shot_type": "full body with cap and gown",
            "lighting": "golden hour soft natural light",
            "background": "academic setting, campus architecture",
            "pose": "proud confident stance with diploma",
            "expression": "genuine happy smile, accomplishment pride",
            "hairstyle": "neat groomed style under graduation cap",
            "outfit": "graduation cap and gown, academic regalia",
            "depth_of_field": "medium depth f/4.0, context included",
            "color_grade": "warm golden tones, celebratory colors",
            "mood": "pride, accomplishment, milestone celebration",
        },
        "prompt_template": """You are capturing a meaningful graduation milestone moment.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and genuine happiness
- Skin tone and natural features
- Eye color and pride expression
- Face shape and age
- Unique personal markers
- Authentic joyful appearance

STYLE REFERENCE (Graduation Ceremony)
Extract exclusively:
- Pose: proud confident stance with diploma
- Expression: genuine happy smile, pride and accomplishment
- Hairstyle: neat groomed style visible under cap
- Outfit: graduation cap and gown, academic regalia
- Lighting: golden hour soft natural light, warm 3800K
- Background: academic campus architecture, institutional setting
- Camera: 50mm lens, milestone distance
- Depth of field: medium f/4.0, context and subject balance
- Color grade: warm golden tones, celebratory mood
- Composition: full body graduation pose, milestone framing

AUTHENTIC MILESTONE MOMENT:
1. User's face recognizably joyful and authentic
2. Graduation styling applied to user's appearance
3. Never merge two different faces
4. Capture genuine achievement pride
5. Timeless graduation memory of user

TECHNICAL REQUIREMENTS:
- Milestone photography standard
- 50mm lens natural perspective
- Golden hour warm lighting
- Medium depth of field f/4.0
- Warm celebratory color grading
- Academic portrait quality
- Joyful authentic emotion
- Timeless graduation aesthetic
- Professional milestone photography

Generate: User's proud graduation moment.""",
    },
    {
        "title": "Wedding Day Portrait",
        "collection": "Wedding",
        "color": (240, 200, 160),
        "style_description": {
            "camera_angle": "slightly above eye level, romantic",
            "lens": "85mm, romantic flattery lens",
            "shot_type": "intimate wedding portrait",
            "lighting": "soft diffused romantic lighting, warm 3500K",
            "background": "romantic venue, flowers, elegant setting",
            "pose": "elegant poised stance, romantic presence",
            "expression": "tender romantic gaze, genuine emotion",
            "hairstyle": "wedding day styled hair, formal elegance",
            "outfit": "wedding attire: bridal gown or formal wear",
            "depth_of_field": "soft romantic bokeh f/2.0",
            "color_grade": "romantic warm tones, soft pink highlights",
            "mood": "romantic elegance, wedding day beauty, emotional depth",
        },
        "prompt_template": """You are a romantic wedding portrait photographer capturing emotional depth.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and genuine emotion
- Skin tone and natural beauty
- Eye color and tender expression
- Face shape and proportions
- Age and romantic character
- Unique personal beauty markers
- Authentic emotional appearance

STYLE REFERENCE (Wedding Day Portrait)
Extract exclusively:
- Pose: elegant poised stance, romantic presence
- Expression: tender romantic gaze, genuine emotion
- Hairstyle: wedding day styled, formal elegance
- Outfit: wedding attire (bridal gown or formal wear)
- Lighting: soft diffused romantic 3500K, gentle falloff
- Background: romantic venue with flowers, elegant setting
- Camera: 85mm lens, romantic distance
- Depth of field: soft romantic bokeh f/2.0, dreamy quality
- Color grade: warm romantic tones, soft pink highlights
- Composition: intimate wedding portrait framing

EMOTIONAL AUTHENTICITY:
1. User's face recognizably beautiful and emotionally genuine
2. Wedding styling applied to user's authentic appearance
3. Never blend two different identities
4. Capture genuine romantic emotion
5. Timeless wedding day portrait of user

TECHNICAL REQUIREMENTS:
- Romantic wedding photography standard
- 85mm lens romantic flattery
- Soft diffused romantic lighting 3500K
- Dreamy bokeh depth f/2.0
- Warm romantic color grading
- Wedding portrait excellence
- Emotional authentic moment
- Timeless romantic aesthetic
- Professional wedding photography

Generate: User's romantic wedding day portrait.""",
    },
    {
        "title": "Fine Art Black & White",
        "collection": "Black & White",
        "color": (128, 128, 128),
        "style_description": {
            "camera_angle": "dimensional, character-revealing",
            "lens": "70mm, classic fine art lens",
            "shot_type": "character-focused close portrait",
            "lighting": "dramatic chiaroscuro, strong directional key light",
            "background": "textured dark background, artistic depth",
            "pose": "contemplative artistic pose",
            "expression": "introspective thoughtful gaze, character depth",
            "hairstyle": "natural authentic hair, sculptural quality",
            "outfit": "monochrome simple clothing, texture focus",
            "depth_of_field": "medium depth f/2.8, artistic focus",
            "color_grade": "fine art black and white, rich tonal range",
            "mood": "artistic contemplation, timeless character study",
        },
        "prompt_template": """You are a fine art portrait photographer creating character studies.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and unique character
- Skin tone and tonal qualities
- Eye depth and expression
- Face shape and proportions
- Age and wisdom lines
- Texture and natural features
- Authentic character markers

STYLE REFERENCE (Fine Art Black & White)
Extract exclusively:
- Pose: contemplative artistic pose, thoughtful positioning
- Expression: introspective thoughtful gaze, character study depth
- Hairstyle: natural authentic hair, sculptural light quality
- Outfit: monochrome simple clothing, texture and form
- Lighting: dramatic chiaroscuro, strong directional key light
- Background: textured dark background, artistic depth
- Camera: 70mm lens, fine art distance
- Depth of field: medium f/2.8, artistic focus on character
- Color grade: fine art black and white, rich tonal range
- Composition: character-focused close portrait, artistic framing

ARTISTIC AUTHENTICITY:
1. User's face recognizably authentic and characterized
2. Fine art treatment applied to user's appearance
3. Never merge two different identities
4. Reveal character through lighting and form
5. Timeless character study of user

TECHNICAL REQUIREMENTS:
- Fine art photography standard
- 70mm lens classic perspective
- Dramatic chiaroscuro lighting technique
- Medium artistic depth f/2.8
- Rich black and white tonal range
- Fine art portrait excellence
- Character and depth emphasis
- Timeless artistic aesthetic
- Professional fine art photography

Generate: User's artistic black and white character study.""",
    },
    {
        "title": "Cinematic Color Grading",
        "collection": "Cinematic",
        "color": (64, 96, 144),
        "style_description": {
            "camera_angle": "cinematic slight angle, filmic quality",
            "lens": "50mm, cinematic natural lens",
            "shot_type": "medium cinematic portrait",
            "lighting": "cinematic multi-layer lighting, teal shadows",
            "background": "cinematic location, atmospheric depth",
            "pose": "cinematic natural pose, film moment",
            "expression": "cinematic engaged gaze, story-driven emotion",
            "hairstyle": "cinematic styled, motion and texture",
            "outfit": "cinematic wardrobe, color and texture harmony",
            "depth_of_field": "cinematic medium f/3.2, layered depth",
            "color_grade": "cinematic teal/orange grading, dramatic mood",
            "mood": "cinematic narrative, film-like quality, dramatic emotion",
        },
        "prompt_template": """You are a cinematic portrait photographer creating film-quality imagery.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and cinematic presence
- Skin tone and cinematic qualities
- Eye color and narrative expression
- Face shape and proportions
- Age and cinematic character
- Unique personal markers
- Authentic cinematic appearance

STYLE REFERENCE (Cinematic Color Grading)
Extract exclusively:
- Pose: cinematic natural pose, film moment feeling
- Expression: cinematic engaged gaze, story-driven emotion
- Hairstyle: cinematic styled, motion and textural quality
- Outfit: cinematic wardrobe, color harmony and texture
- Lighting: cinematic multi-layer, teal shadow accent light
- Background: cinematic location, atmospheric depth layers
- Camera: 50mm lens, cinematic natural distance
- Depth of field: cinematic medium f/3.2, layered depth
- Color grade: cinematic teal/orange, dramatic mood and tone
- Composition: medium cinematic framing, narrative quality

CINEMATIC AUTHENTICITY:
1. User's face recognizably cinematic and present
2. Cinematic styling applied to user's appearance
3. Never merge two different faces
4. Create film-quality narrative moment
5. User as cinematic protagonist

TECHNICAL REQUIREMENTS:
- Cinematic photography standard
- 50mm lens cinematic framing
- Layered cinematic lighting technique
- Cinematic depth of field f/3.2
- Teal/orange cinematic grading
- Film-quality color science
- Narrative emotional depth
- Cinematic atmospheric quality
- Professional cinematic photography

Generate: User's cinematic portrait moment.""",
    },
    {
        "title": "Travel Adventure Portrait",
        "collection": "Travel",
        "color": (144, 120, 80),
        "style_description": {
            "camera_angle": "natural adventurous angle",
            "lens": "35mm, travel documentary lens",
            "shot_type": "environmental full-body travel portrait",
            "lighting": "natural travel lighting, mixed sources",
            "background": "iconic travel location, cultural landmark",
            "pose": "adventurous confident travel pose",
            "expression": "genuine exploration joy, wanderlust gaze",
            "hairstyle": "natural travel-ready style",
            "outfit": "travel casual wear, adventure appropriate",
            "depth_of_field": "environmental context f/5.6",
            "color_grade": "warm travel palette, location authentic",
            "mood": "adventurous spirit, wanderlust exploration, travel joy",
        },
        "prompt_template": """You are a travel photography specialist capturing adventure moments.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and adventurous spirit
- Skin tone and travel features
- Eye color and exploration expression
- Face shape and proportions
- Age and adventure character
- Natural personal markers
- Authentic travel appearance

STYLE REFERENCE (Travel Adventure Portrait)
Extract exclusively:
- Pose: adventurous confident travel pose, explorer stance
- Expression: genuine exploration joy, wanderlust gaze
- Hairstyle: natural travel-ready style, authentic
- Outfit: travel casual wear, adventure appropriate clothing
- Lighting: natural travel lighting, mixed cultural sources
- Background: iconic travel location, cultural landmark
- Camera: 35mm lens, travel documentary perspective
- Depth of field: environmental context f/5.6, story inclusion
- Color grade: warm travel palette, location authentic tones
- Composition: environmental full-body, travel narrative

TRAVEL AUTHENTICITY:
1. User's face recognizably joyful and adventurous
2. Travel styling applied to user's appearance
3. Never merge two different identities
4. Capture genuine exploration spirit
5. User as travel photographer subject

TECHNICAL REQUIREMENTS:
- Travel photography standard
- 35mm lens documentary perspective
- Natural mixed travel lighting
- Environmental context f/5.6
- Warm travel authentic colors
- Travel photography quality
- Documentary authentic feeling
- Cultural location integration
- Professional travel photography

Generate: User's travel adventure portrait.""",
    },
    {
        "title": "Nature & Outdoor Lifestyle",
        "collection": "Nature",
        "color": (96, 128, 96),
        "style_description": {
            "camera_angle": "natural outdoor angle, environmental connection",
            "lens": "50mm, nature portrait lens",
            "shot_type": "full body in natural environment",
            "lighting": "natural outdoor light, golden hour warmth",
            "background": "natural landscape, forest or nature setting",
            "pose": "relaxed nature-connected pose, authentic movement",
            "expression": "peaceful natural expression, earth connection",
            "hairstyle": "natural relaxed hair, outdoor appropriate",
            "outfit": "outdoor lifestyle wear, nature-appropriate clothing",
            "depth_of_field": "environmental blend f/4.5, nature context",
            "color_grade": "natural earth tones, organic color palette",
            "mood": "peaceful nature connection, outdoor lifestyle, earth harmony",
        },
        "prompt_template": """You are a nature and outdoor lifestyle photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and peaceful presence
- Skin tone and natural beauty
- Eye color and connection expression
- Face shape and proportions
- Age and natural character
- Unique personal markers
- Authentic nature appearance

STYLE REFERENCE (Nature & Outdoor Lifestyle)
Extract exclusively:
- Pose: relaxed nature-connected pose, authentic outdoor movement
- Expression: peaceful natural expression, earth connection
- Hairstyle: natural relaxed hair, outdoor appropriate style
- Outfit: outdoor lifestyle wear, nature-appropriate clothing
- Lighting: natural outdoor golden hour light, warm warmth
- Background: natural landscape, forest or mountain setting
- Camera: 50mm lens, nature portrait perspective
- Depth of field: environmental blend f/4.5, nature context
- Color grade: natural earth tones, organic color palette
- Composition: full body in natural environment, lifestyle narrative

NATURE AUTHENTICITY:
1. User's face recognizably peaceful and connected
2. Nature styling applied to user's appearance
3. Never merge two different identities
4. Capture earth connection and outdoor joy
5. User as nature lifestyle subject

TECHNICAL REQUIREMENTS:
- Nature photography standard
- 50mm lens nature portrait
- Golden hour natural lighting
- Environmental blend f/4.5
- Organic earth tone colors
- Nature photography quality
- Peaceful authentic connection
- Natural landscape integration
- Professional nature photography

Generate: User's nature and outdoor lifestyle portrait.""",
    },
    {
        "title": "Beach Sunset Lifestyle",
        "collection": "Beach",
        "color": (224, 144, 80),
        "style_description": {
            "camera_angle": "relaxed beach angle, sunset perspective",
            "lens": "35mm, beach lifestyle lens",
            "shot_type": "full body beach portrait, lifestyle moment",
            "lighting": "golden sunset light, warm backlighting",
            "background": "beach landscape, ocean sunset, golden hour",
            "pose": "relaxed beach pose, sunset contemplation",
            "expression": "serene beach gaze, sunset peace",
            "hairstyle": "windswept beach hair, natural ocean texture",
            "outfit": "beach wear, summer casual elegance",
            "depth_of_field": "beach environment f/5.0, context included",
            "color_grade": "warm golden sunset tones, beach radiance",
            "mood": "serene beach peace, sunset romance, coastal lifestyle",
        },
        "prompt_template": """You are a beach and sunset lifestyle photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and beach presence
- Skin tone and sunset glow
- Eye color and serene expression
- Face shape and proportions
- Age and beach character
- Unique personal markers
- Authentic beach appearance

STYLE REFERENCE (Beach Sunset Lifestyle)
Extract exclusively:
- Pose: relaxed beach pose, sunset contemplation stance
- Expression: serene beach gaze, sunset peace and calm
- Hairstyle: windswept beach hair, natural ocean texture
- Outfit: beach wear, summer casual elegance
- Lighting: golden sunset light, warm backlighting glow
- Background: beach landscape, ocean sunset, golden hour
- Camera: 35mm lens, beach lifestyle perspective
- Depth of field: beach environment f/5.0, context included
- Color grade: warm golden sunset tones, beach radiance
- Composition: full body beach portrait, lifestyle narrative

BEACH AUTHENTICITY:
1. User's face recognizably serene and present
2. Beach styling applied to user's appearance
3. Never merge two different identities
4. Capture sunset peace and coastal joy
5. User as beach lifestyle subject

TECHNICAL REQUIREMENTS:
- Beach photography standard
- 35mm lens beach lifestyle
- Golden sunset backlighting
- Beach environment f/5.0
- Warm sunset color tones
- Beach photography quality
- Serene peaceful mood
- Sunset ocean integration
- Professional beach photography

Generate: User's beach sunset lifestyle portrait.""",
    },
    {
        "title": "Urban Cafe Culture",
        "collection": "Cafe",
        "color": (160, 120, 96),
        "style_description": {
            "camera_angle": "candid cafe angle, intimate moment",
            "lens": "50mm, cafe environment lens",
            "shot_type": "three-quarter portrait in cafe setting",
            "lighting": "soft cafe ambient light, warm tungsten",
            "background": "cozy cafe interior, coffee shop aesthetic",
            "pose": "relaxed cafe pose, seated or standing casual",
            "expression": "warm authentic cafe moment expression",
            "hairstyle": "natural casual everyday style",
            "outfit": "casual cafe wear, comfortable style",
            "depth_of_field": "cafe integration f/3.5, ambiance blur",
            "color_grade": "warm cafe tones, cozy intimate palette",
            "mood": "cozy intimacy, urban cafe culture, warm connection",
        },
        "prompt_template": """You are a cafe culture and urban lifestyle photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and cafe presence
- Skin tone and warm glow
- Eye color and authentic expression
- Face shape and proportions
- Age and cafe character
- Unique personal markers
- Authentic cafe appearance

STYLE REFERENCE (Urban Cafe Culture)
Extract exclusively:
- Pose: relaxed cafe pose, seated or standing casual moment
- Expression: warm authentic cafe moment expression
- Hairstyle: natural casual everyday style, effortless
- Outfit: casual cafe wear, comfortable authentic style
- Lighting: soft cafe ambient light, warm tungsten
- Background: cozy cafe interior, coffee shop aesthetic
- Camera: 50mm lens, cafe intimate perspective
- Depth of field: cafe integration f/3.5, ambiance blur
- Color grade: warm cafe tones, cozy intimate palette
- Composition: three-quarter portrait, cafe lifestyle narrative

CAFE AUTHENTICITY:
1. User's face recognizably warm and authentic
2. Cafe styling applied to user's appearance
3. Never merge two different identities
4. Capture cozy urban moment
5. User as cafe culture subject

TECHNICAL REQUIREMENTS:
- Cafe photography standard
- 50mm lens cafe intimacy
- Warm ambient cafe lighting
- Cafe integration f/3.5
- Warm cozy color tones
- Cafe photography quality
- Authentic intimate mood
- Cafe interior integration
- Professional cafe photography

Generate: User's urban cafe culture portrait.""",
    },
    {
        "title": "Studio Fashion Editorial",
        "collection": "Studio",
        "color": (96, 96, 112),
        "style_description": {
            "camera_angle": "studio professional centered",
            "lens": "85mm, studio fashion lens",
            "shot_type": "fashion editorial full-length studio",
            "lighting": "professional studio 3-point lighting setup",
            "background": "seamless studio backdrop, neutral or colored",
            "pose": "fashion editorial pose, style showcase",
            "expression": "confident fashion focus, editorial poise",
            "hairstyle": "editorial styled hair, fashion perfection",
            "outfit": "designer fashion piece, editorial styling",
            "depth_of_field": "studio perfect focus f/2.8",
            "color_grade": "studio controlled color, editorial perfection",
            "mood": "studio fashion excellence, editorial sophistication",
        },
        "prompt_template": """You are a studio fashion and editorial photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and fashion presence
- Skin tone and studio lighting qualities
- Eye color and editorial expression
- Face shape and proportions
- Age and fashion character
- Unique personal markers
- Authentic studio appearance

STYLE REFERENCE (Studio Fashion Editorial)
Extract exclusively:
- Pose: fashion editorial pose, style showcase stance
- Expression: confident fashion focus, editorial poise
- Hairstyle: editorial styled hair, fashion perfection
- Outfit: designer fashion piece, editorial styling
- Lighting: professional studio 3-point lighting setup
- Background: seamless studio backdrop, neutral or colored
- Camera: 85mm lens, studio fashion distance
- Depth of field: studio perfect focus f/2.8, precision
- Color grade: studio controlled color, editorial perfection
- Composition: full-length fashion editorial, style narrative

STUDIO AUTHENTICITY:
1. User's face recognizably confident and fashionable
2. Studio fashion styling applied to user's appearance
3. Never merge two different identities
4. Showcase fashion and editorial excellence
5. User as fashion editorial subject

TECHNICAL REQUIREMENTS:
- Studio fashion standard
- 85mm lens studio fashion
- Professional 3-point studio lighting
- Studio perfect focus f/2.8
- Controlled editorial color
- Studio fashion photography quality
- Editorial poise and sophistication
- Seamless studio integration
- Professional studio photography

Generate: User's studio fashion editorial portrait.""",
    },
    {
        "title": "Festive Celebration Moment",
        "collection": "Festive",
        "color": (200, 96, 96),
        "style_description": {
            "camera_angle": "joyful celebration angle, festive cheer",
            "lens": "50mm, celebration lens",
            "shot_type": "celebratory full-body portrait",
            "lighting": "festive warm lighting, celebration glow",
            "background": "festive holiday setting, celebration environment",
            "pose": "joyful celebration pose, festive confidence",
            "expression": "genuine joyful grin, festive happiness",
            "hairstyle": "festive appropriate styling, celebration ready",
            "outfit": "festive holiday attire, celebration wear",
            "depth_of_field": "celebration context f/4.0, festive ambiance",
            "color_grade": "warm festive palette, celebration colors",
            "mood": "joyful celebration, festive happiness, holiday spirit",
        },
        "prompt_template": """You are a celebration and festive moment photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and joyful spirit
- Skin tone and celebration glow
- Eye color and happiness expression
- Face shape and proportions
- Age and festive character
- Unique personal markers
- Authentic celebration appearance

STYLE REFERENCE (Festive Celebration Moment)
Extract exclusively:
- Pose: joyful celebration pose, festive confidence stance
- Expression: genuine joyful grin, festive happiness
- Hairstyle: festive appropriate styling, celebration ready
- Outfit: festive holiday attire, celebration wear
- Lighting: festive warm lighting, celebration glow
- Background: festive holiday setting, celebration environment
- Camera: 50mm lens, celebration distance
- Depth of field: celebration context f/4.0, festive ambiance
- Color grade: warm festive palette, celebration colors
- Composition: celebratory full-body, festive narrative

CELEBRATION AUTHENTICITY:
1. User's face recognizably joyful and celebrating
2. Festive styling applied to user's appearance
3. Never merge two different identities
4. Capture genuine celebration joy
5. User as celebration subject

TECHNICAL REQUIREMENTS:
- Celebration photography standard
- 50mm lens celebration perspective
- Warm festive lighting
- Celebration context f/4.0
- Warm festive color palette
- Celebration photography quality
- Joyful authentic happiness
- Holiday environment integration
- Professional celebration photography

Generate: User's festive celebration portrait.""",
    },
    {
        "title": "Fitness & Athletic Portrait",
        "collection": "Fitness",
        "color": (144, 160, 176),
        "style_description": {
            "camera_angle": "athletic confident angle, strength showcase",
            "lens": "70mm, athletic flattery lens",
            "shot_type": "athletic full-body portrait",
            "lighting": "dramatic athletic lighting, strength definition",
            "background": "fitness studio or athletic environment",
            "pose": "confident athletic pose, strength and fitness showcase",
            "expression": "confident athletic gaze, fit determination",
            "hairstyle": "athletic practical style, clean groomed",
            "outfit": "athletic wear, fitness appropriate styling",
            "depth_of_field": "athletic definition f/3.5, form clarity",
            "color_grade": "athletic vibrant palette, health glow",
            "mood": "confident athletic strength, fitness achievement, vitality",
        },
        "prompt_template": """You are a fitness and athletic portrait photographer.

PRIMARY REFERENCE (User's Face)
Preserve exclusively:
- Facial identity and athletic presence
- Skin tone and healthy glow
- Eye color and confident expression
- Face shape and proportions
- Age and athletic character
- Unique personal markers
- Authentic athletic appearance

STYLE REFERENCE (Fitness & Athletic Portrait)
Extract exclusively:
- Pose: confident athletic pose, strength and fitness showcase
- Expression: confident athletic gaze, fit determination
- Hairstyle: athletic practical style, clean groomed
- Outfit: athletic wear, fitness appropriate styling
- Lighting: dramatic athletic lighting, strength definition
- Background: fitness studio or athletic environment
- Camera: 70mm lens, athletic flattery distance
- Depth of field: athletic definition f/3.5, form clarity
- Color grade: athletic vibrant palette, health glow
- Composition: athletic full-body, fitness narrative

ATHLETIC AUTHENTICITY:
1. User's face recognizably confident and athletic
2. Athletic styling applied to user's appearance
3. Never merge two different identities
4. Showcase fitness achievement and strength
5. User as athletic subject

TECHNICAL REQUIREMENTS:
- Athletic photography standard
- 70mm lens athletic flattery
- Dramatic athletic lighting
- Athletic definition f/3.5
- Vibrant health color palette
- Athletic photography quality
- Confident strength presentation
- Fitness environment integration
- Professional athletic photography

Generate: User's fitness and athletic portrait.""",
    },
]

CATEGORIES = [
    "Luxury",
    "Old Money",
    "Editorial",
    "Street Fashion",
    "Korean",
    "Business",
    "Graduation",
    "Wedding",
    "Black & White",
    "Cinematic",
    "Travel",
    "Nature",
    "Beach",
    "Cafe",
    "Studio",
    "Festive",
    "Fitness",
]

COMMON_PROMPT_TEMPLATE = """
CRITICAL IDENTITY PRESERVATION RULES
====================================
These rules apply to ALL reference photo presets.

PRIMARY REFERENCE IMAGE (User's Face)
Extract and preserve EXCLUSIVELY:
- Facial identity and recognizable features
- Skin tone and texture qualities
- Eye color and depth
- Nose shape and unique geometry
- Lip color and shape
- Jawline and face shape
- Age and life experience markers
- Hairline and hair color
- All unique personal distinguishing features
- Authentic natural appearance

STYLE REFERENCE IMAGE (Photography Style)
Extract EXCLUSIVELY:
- Pose and body positioning
- Hairstyle and hair direction
- Expression and gaze direction
- Outfit and clothing choices
- Lighting direction and quality
- Background environment
- Camera angle and lens perspective
- Depth of field and bokeh
- Color grading and tonal treatment
- Composition and framing
- Mood and atmosphere
- Any other styling elements

ABSOLUTE RULES
==============
1. User's FACE must be 100% recognizably authentic to themselves
2. Copy ONLY pose, outfit, lighting, background, mood from style reference
3. NEVER blend two different faces or identities
4. NEVER merge facial features from different people
5. NEVER alter facial proportions or structure
6. NEVER change facial identity in any way
7. The user must be unmistakably recognizable in final image
8. It must look like user naturally participated in this photoshoot
9. Professional photography quality on all technical aspects
10. Authentic natural appearance is non-negotiable

QUALITY REQUIREMENTS
====================
- Professional photoshoot quality standard
- Sharp focus on facial features and eyes
- Proper lighting technique and shadow placement
- Authentic color grading without distortion
- Natural skin texture enhancement only
- Professional retouching standards
- No artifacts, distortions, or merging artifacts
- 8K resolution quality output
- Seamless style application to user's authentic face
- Timeless professional photography aesthetic
"""


def _validate_preset(preset: dict) -> bool:
    """Validate preset has all required fields and proper structure."""
    required_fields = ["title", "collection", "style_description", "prompt_template", "color"]
    required_style_fields = [
        "camera_angle", "lens", "shot_type", "lighting", "background",
        "pose", "expression", "hairstyle", "outfit", "depth_of_field",
        "color_grade", "mood"
    ]
    
    # Check required top-level fields
    for field in required_fields:
        if field not in preset or not preset[field]:
            logger.error("Missing field '%s' in preset: %s", field, preset.get("title"))
            return False
    
    # Validate title
    title = preset.get("title", "")
    if not title or len(title) > 255:
        logger.error("Invalid title length for preset: %s", title)
        return False
    
    # Validate color
    color = preset.get("color", ())
    if len(color) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in color):
        logger.error("Invalid color tuple for preset '%s': %s", title, color)
        return False
    
    # Check required style fields
    style_desc = preset.get("style_description", {})
    for field in required_style_fields:
        if field not in style_desc:
            logger.error("Missing style field '%s' in preset '%s'", field, title)
            return False
    
    return True


def _placeholder_thumbnail(title: str, color: tuple[int, int, int]) -> Optional[bytes]:
    """Generate placeholder thumbnail. Returns None if generation fails."""
    try:
        # Validate color tuple
        if len(color) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in color):
            logger.error("Invalid color tuple: %s", color)
            return None
        
        # Create image
        image = Image.new("RGB", (640, 800), color)
        if not image:
            logger.error("Failed to create image for '%s'", title)
            return None
        
        draw = ImageDraw.Draw(image)
        
        # Load font
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        except OSError as exc:
            logger.warning("Font not found, using default: %s", exc)
            font = ImageFont.load_default()
        
        # Draw text
        draw.multiline_text((40, 700), title, fill="white", font=font)
        
        # Save to bytes
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        
        thumb_bytes = buf.getvalue()
        if not thumb_bytes or len(thumb_bytes) == 0:
            logger.error("Generated empty thumbnail for '%s'", title)
            return None
        
        logger.debug("✅ Generated thumbnail for '%s' (%d bytes)", title, len(thumb_bytes))
        return thumb_bytes
    except Exception as exc:
        logger.error("Thumbnail generation failed for '%s': %s", title, exc)
        return None


def seed() -> None:
    """Seed database with production-quality reference photo presets."""
    logger.info("Starting database seed...")
    
    # 1. Validate settings
    try:
        settings = get_settings()
        if not settings.storage_dir.exists():
            logger.error("❌ Storage directory not found: %s", settings.storage_dir)
            sys.exit(1)
        logger.info("✅ Settings validated")
    except Exception as exc:
        logger.error("❌ Settings validation failed: %s", exc)
        sys.exit(1)
    
    # 2. Validate database connection
    try:
        if not check_db_connection():
            raise RuntimeError("Database connectivity check failed")
        logger.info("✅ Database connection validated")
    except Exception as exc:
        logger.error("❌ Database connection failed: %s", exc)
        sys.exit(1)
    
    # 3. Create schema
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database schema created")
    except Exception as exc:
        logger.error("❌ Schema creation failed: %s", exc)
        sys.exit(1)
    
    # 4. Seed presets
    db = SessionLocal()
    try:
        existing_titles = set(db.scalars(select(ReferencePhoto.title)).all())
        logger.info("Existing presets in DB: %s", existing_titles)
        
        created = 0
        
        for preset in PLACEHOLDER_PRESETS:
            # Validate preset structure
            if not _validate_preset(preset):
                logger.warning("Skipping invalid preset: %s", preset.get("title"))
                continue
            
            # Skip if already exists
            if preset["title"] in existing_titles:
                logger.debug("Skipping existing preset: '%s'", preset["title"])
                continue
            
            # Generate thumbnail
            color = preset["color"]
            thumb_bytes = _placeholder_thumbnail(preset["title"], color)
            if not thumb_bytes:
                logger.warning("Skipping preset with failed thumbnail: '%s'", preset["title"])
                continue
            
            # Upload thumbnail with unique filename
            try:
                preset_id = hashlib.md5(preset["title"].encode()).hexdigest()[:8]
                filename = f"preset_{preset_id}.jpg"
                thumbnail_url = storage.save_bytes("thumbnails", filename, thumb_bytes)
                logger.info("Thumbnail uploaded: %s", thumbnail_url)
            except Exception as exc:
                logger.error("Failed to upload thumbnail for '%s': %s", preset["title"], exc)
                continue
            
            # Add to database
            try:
                db.add(
                    ReferencePhoto(
                        title=preset["title"],
                        collection=preset["collection"],
                        thumbnail_url=thumbnail_url,
                        style_description=preset["style_description"],
                        prompt_template=preset["prompt_template"],
                        active=True,
                    )
                )
                created += 1
                logger.info("Created preset: '%s'", preset["title"])
            except Exception as exc:
                db.rollback()
                logger.error("Failed to save preset '%s': %s", preset["title"], exc)
                continue
        
        # Seed default test accounts
        _seed_default_users(db)

        # Commit all at once
        try:
            db.commit()
            logger.info("✅ Seed complete: created=%d presets, total_presets=%d", created, len(PLACEHOLDER_PRESETS))
        except Exception as exc:
            db.rollback()
            logger.error("❌ Commit failed: %s", exc)
            sys.exit(1)
    
    except Exception as exc:
        logger.error("❌ Seed failed: %s", exc)
        sys.exit(1)
    finally:
        db.close()


def _seed_default_users(db) -> None:
    """Seed default verified test accounts for instant development testing."""
    default_users = [
        {
            "email": "admin@diva.ai",
            "password": "Admin@123456",
            "display_name": "Diva Admin",
            "is_email_verified": True,
        },
        {
            "email": "demo@diva.ai",
            "password": "Demo@123456",
            "display_name": "Demo User",
            "is_email_verified": True,
        },
    ]

    for udata in default_users:
        existing = db.scalars(select(User).where(User.email == udata["email"])).first()
        if existing:
            logger.debug("Test user already exists: %s", udata["email"])
            continue

        user = User(
            email=udata["email"],
            password_hash=hash_password(udata["password"]),
            display_name=udata["display_name"],
            is_email_verified=udata["is_email_verified"],
            is_active=True,
        )
        db.add(user)
        logger.info("🔑 Seeded default test account: email=%s (password: %s)", udata["email"], udata["password"])


# Print available presets
print("Production-Quality Reference Photo Presets")
print("=" * 50)
print(f"Total presets available: {len(PLACEHOLDER_PRESETS)}")
print("\nCategories:")
for c in CATEGORIES:
    print(f"  • {c}")
print("\nEach preset includes:")
print("  • Detailed style_description with technical photography parameters")
print("  • High-quality prompt_template with identity preservation rules")
print("  • Professional photoshoot guidance")
print("  • Specific lighting, pose, expression, outfit details")
print("\nAll prompts emphasize: User's face 100% authentic + Style reference only")
print("\n" + "=" * 50)


if __name__ == "__main__":
    seed()