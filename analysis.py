import re
from collections import Counter
from utils.text_utils import multi_phrase_count
from utils.logger import get_logger
from typing import Union
from models import SEORequirements

# logger setup
logger = get_logger(__name__)

def analyze_content(markdown_content: str, requirements: Union[SEORequirements, dict]):
    """
    Analyze SEO content to check if it meets all requirements.
    
    Args:
        markdown_content (str): The markdown content to analyze
        requirements (dict): The SEO requirements dictionary
        
    Returns:
        dict: Analysis results including keyword counts, heading structure, etc.
    """
    
    # Clean the text for analysis (remove markdown syntax, HTML, etc.)
    CLEAN_RE = re.compile(r'^#+.*$|[*_`~]|[<][^>]+[>]|https?://\S+|[\n\r.,;:!?()\[\]{}"\'-]', re.MULTILINE)
    text_content = CLEAN_RE.sub(' ', markdown_content.lower())
    # Normalize whitespace
    text_content = re.sub(r'\s+', ' ', text_content).strip()
    # Create a word list for exact matching
    tokens = text_content.split()
    # Create a normalized string with spaces for substring searching
    joined_text = ' ' + ' '.join(tokens) + ' '
    # Create raw text with punctuation removed for broader matching
    raw_text = re.sub(r'[^a-z0-9\s]', ' ', markdown_content.lower())
    raw_text = re.sub(r'\s+', ' ', raw_text).strip()
    word_counts = Counter(tokens)

    # Count images in content
    image_count = len(re.findall(r'!\[.*?\]\(.*?\)', markdown_content))
    
    # Get total required images from basic tunings
    required_images = 0
    if isinstance(requirements, SEORequirements) and hasattr(requirements, 'basic_tunings'):
        required_images = requirements.basic_tunings.get('Number of Images', 0)
    elif isinstance(requirements, dict):
        # Try different possible paths to find the image count requirement
        if 'basic_tunings' in requirements and isinstance(requirements['basic_tunings'], dict):
            required_images = requirements['basic_tunings'].get('Number of Images', 0)
        elif 'Number of Images' in requirements:
            required_images = requirements.get('Number of Images', 0)
    
    # Initialize analysis result structure
    req_dict = requirements.to_dict() if isinstance(requirements, SEORequirements) else requirements

    # Try to get meta title and description, either from meta_and_headings in requirements or from requirements directly
    meta_title = ""
    meta_description = ""
    
    # First check if meta_and_headings exists in the requirements dictionary
    if 'meta_and_headings' in req_dict and isinstance(req_dict['meta_and_headings'], dict):
        meta_title = req_dict['meta_and_headings'].get('meta_title', '')
        meta_description = req_dict['meta_and_headings'].get('meta_description', '')
    # Then check if they're directly in the requirements dictionary
    else:
        meta_title = req_dict.get('meta_title', '')
        meta_description = req_dict.get('meta_description', '')
    
    # Create the analysis structure
    analysis = {
        "primary_keyword": req_dict.get("primary_keyword", ""),
        "primary_keyword_count": 0,
        "word_count": len(tokens),
        "word_count_target": req_dict.get("word_count", 1500),
        "word_count_met": len(tokens) >= req_dict.get("word_count", 1500),
        "variations": {},
        "heading_structure": {"H1": 0, "H2": 0, "H3": 0, "H4": 0, "H5": 0, "H6": 0},
        "lsi_keywords": {},
        "entities": {},
        "meta_title": meta_title,
        "meta_description": meta_description,
        "image_count": image_count,
        "required_images": required_images,
        "images_met": image_count >= required_images
    }

    # Check primary keyword usage
    primary_keyword = req_dict.get("primary_keyword", "").lower().strip()
    if primary_keyword and primary_keyword not in ["", None]:
        # Use multiple counting approaches and take the higher count for accuracy
        # 1. Direct string match in normalized text
        count1 = raw_text.count(' ' + primary_keyword + ' ')
        # 2. Word boundary regex for more precise matching
        primary_keyword_pattern = r'\b' + re.escape(primary_keyword) + r'\b'
        count2 = len(re.findall(primary_keyword_pattern, raw_text))
        # 3. Check for exact matches in token list (most accurate for single words)
        count3 = 0
        if ' ' not in primary_keyword:
            count3 = word_counts.get(primary_keyword, 0)
        
        # Take the highest count from the different methods
        analysis["primary_keyword_count"] = max(count1, count2, count3)
        
        # Calculate primary keyword density
        if analysis["word_count"] > 0:
            analysis["primary_keyword_density"] = round((analysis["primary_keyword_count"] / analysis["word_count"]) * 100, 2)
        else:
            analysis["primary_keyword_density"] = 0

    # Check variations usage
    variations = req_dict.get("variations", [])
    
    # Get all entities from both regular and custom sources
    entities = req_dict.get("entities", [])
    custom_entities = req_dict.get("custom_entities", [])
    
    # Merge entities and custom entities, ensuring no duplicates
    all_entities = []
    # Add custom entities first (they should take priority)
    all_entities.extend(custom_entities)
    # Add regular entities that aren't already in the list
    for entity in entities:
        if entity not in all_entities:
            all_entities.append(entity)

    # Improved phrase counting for variations and entities
    def count_phrase(text, phrase):
        """Count occurrences of a phrase using multiple methods for accuracy"""
        phrase = phrase.lower().strip()
        # 1. Direct string match with spaces
        count1 = text.count(' ' + phrase + ' ')
        # 2. Word boundary regex match
        pattern = r'\b' + re.escape(phrase) + r'\b'
        count2 = len(re.findall(pattern, raw_text))
        # Return the higher count
        return max(count1, count2)
    
    # Count all variations and entities
    phrase_counts = {phrase.lower().strip(): count_phrase(raw_text, phrase) 
                     for phrase in variations + all_entities}

    # Fill variation counts with density calculation
    total_variation_count = 0
    for var in variations:
        count = phrase_counts.get(var.lower().strip(), 0)
        density = (count / analysis["word_count"]) * 100 if analysis["word_count"] > 0 else 0
        analysis["variations"][var] = {
            "count": count,
            "density": round(density, 2),
            "met": count > 0
        }
        total_variation_count += count
    
    # Add total variations density
    if variations:
        analysis["total_variation_count"] = total_variation_count
        analysis["total_variation_density"] = round((total_variation_count / analysis["word_count"]) * 100, 2) if analysis["word_count"] > 0 else 0

    # Check LSI keywords usage with density calculation
    lsi_keywords = req_dict.get("lsi_keywords", {})
    total_lsi_count = 0
    if isinstance(lsi_keywords, dict):
        for keyword, target in lsi_keywords.items():
            keyword_lower = keyword.lower().strip()
            keyword_count = phrase_counts.get(keyword_lower, 0)
            
            # Handle different formats of LSI keyword requirements
            target_count = 1  # Default
            if isinstance(target, dict) and 'count' in target:
                target_count = target['count']
            elif isinstance(target, int):
                target_count = target
            
            # Calculate density
            density = (keyword_count / analysis["word_count"]) * 100 if analysis["word_count"] > 0 else 0
                
            analysis["lsi_keywords"][keyword] = {
                "count": keyword_count,
                "target": target_count,
                "met": keyword_count >= target_count,
                "density": round(density, 2)
            }
            total_lsi_count += keyword_count
    else:
        # Handle list format
        for keyword in lsi_keywords:
            keyword_lower = keyword.lower().strip()
            keyword_count = phrase_counts.get(keyword_lower, 0)
            density = (keyword_count / analysis["word_count"]) * 100 if analysis["word_count"] > 0 else 0
            
            analysis["lsi_keywords"][keyword] = {
                "count": keyword_count,
                "target": 1,  # Default to 1 for list format
                "met": keyword_count >= 1,
                "density": round(density, 2)
            }
            total_lsi_count += keyword_count
    
    # Add total LSI keywords density
    if lsi_keywords:
        analysis["total_lsi_count"] = total_lsi_count
        analysis["total_lsi_density"] = round((total_lsi_count / analysis["word_count"]) * 100, 2) if analysis["word_count"] > 0 else 0

    # Check entities usage with density calculation
    total_entity_count = 0
    for entity in all_entities:
        entity_lower = entity.lower().strip()
        entity_count = phrase_counts.get(entity_lower, 0)
        density = (entity_count / analysis["word_count"]) * 100 if analysis["word_count"] > 0 else 0
        
        analysis["entities"][entity] = {
            "count": entity_count,
            "met": entity_count > 0,
            "density": round(density, 2)
        }
        total_entity_count += entity_count
    
    # Add total entities density
    if all_entities:
        analysis["total_entity_count"] = total_entity_count
        analysis["total_entity_density"] = round((total_entity_count / analysis["word_count"]) * 100, 2) if analysis["word_count"] > 0 else 0

    # Extract heading tags
    headings = {
        "H1": len(re.findall(r'^# ', markdown_content, re.MULTILINE)),
        "H2": len(re.findall(r'^## ', markdown_content, re.MULTILINE)),
        "H3": len(re.findall(r'^### ', markdown_content, re.MULTILINE)),
        "H4": len(re.findall(r'^#### ', markdown_content, re.MULTILINE)),
        "H5": len(re.findall(r'^##### ', markdown_content, re.MULTILINE)),
        "H6": len(re.findall(r'^###### ', markdown_content, re.MULTILINE))
    }
    
    # Update heading structure
    analysis["heading_structure"] = headings
    
    # Check if heading requirements are met
    heading_requirements = {
        "H1": 1,  # We generally want 1 H1 tag
        "H2": 0,
        "H3": 0,
        "H4": 0,
        "H5": 0,
        "H6": 0
    }
    
    # Get heading structure requirements from requirements
    # Look for multiple formats of heading structure requirements
    
    # First check direct requirement keys
    for h_type in ["H2", "H3", "H4", "H5", "H6"]:
        key = f"Number of {h_type} tags"
        if key in req_dict:
            heading_requirements[h_type] = req_dict[key]
            
    # Then check in requirements sub-dictionary if it exists
    if 'requirements' in req_dict and isinstance(req_dict['requirements'], dict):
        for h_type in ["H2", "H3", "H4", "H5", "H6"]:
            key = f"Number of {h_type} tags"
            if key in req_dict['requirements']:
                heading_requirements[h_type] = req_dict['requirements'][key]
                
    # Finally check in heading_structure if it exists
    if 'heading_structure' in req_dict and isinstance(req_dict['heading_structure'], dict):
        for h_type in ["H2", "H3", "H4", "H5", "H6"]:
            if h_type in req_dict['heading_structure']:
                heading_requirements[h_type] = req_dict['heading_structure'][h_type]
    
    analysis["heading_requirements"] = heading_requirements
    
    # Calculate score based on requirements met
    score_components = []
    
    # Word count score (20%)
    word_count_score = 20 if analysis["word_count_met"] else round(20 * (analysis["word_count"] / analysis["word_count_target"]))
    score_components.append(("Word Count", word_count_score, 20))
    
    # Primary keyword score (20%)
    primary_keyword_score = 20 if analysis["primary_keyword_count"] > 0 else 0
    score_components.append(("Primary Keyword", primary_keyword_score, 20))
    
    # Heading structure score (20%)
    # Calculate percentage of heading requirements met
    headings_met = sum(1 for h_type in heading_requirements if analysis["heading_structure"].get(h_type, 0) >= heading_requirements.get(h_type, 0))
    heading_score = round(20 * (headings_met / len(heading_requirements)))
    score_components.append(("Heading Structure", heading_score, 20))
    
    # LSI keywords score (20%)
    if analysis["lsi_keywords"]:
        lsi_met = sum(1 for info in analysis["lsi_keywords"].values() if info["met"])
        lsi_score = round(20 * (lsi_met / len(analysis["lsi_keywords"])))
    else:
        lsi_score = 20  # No LSI keywords required
    score_components.append(("LSI Keywords", lsi_score, 20))
    
    # Entities score (20%)
    if analysis["entities"]:
        entities_met = sum(1 for info in analysis["entities"].values() if info["met"])
        entity_score = round(20 * (entities_met / len(analysis["entities"])))
    else:
        entity_score = 20  # No entities required
    score_components.append(("Entities", entity_score, 20))
    
    # Calculate final score
    analysis["score"] = word_count_score + primary_keyword_score + heading_score + lsi_score + entity_score
    analysis["score_components"] = score_components
    
    logger.info(f"Content analysis complete. Score: {analysis['score']}%")
    return analysis
