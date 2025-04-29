import streamlit as st
import pandas as pd
import re
import json
import warnings
from seo_parser import parse_cora_report
from services import (
    generate_meta_and_headings,
    markdown_to_html,
    generate_content_from_headings,
    analyze_content
)
from content_generator import extract_markdown_content
from utils.logger import get_logger
from ui_components import (
    initialize_session_state,
    display_token_usage,
    render_extracted_data,
    display_generated_content,
    create_download_zip,
    stream_content_display
)
from models import SEORequirements

def extract_headings_from_content(content):
    """Extract headings from Claude's response content."""
    heading_index = content.find("HEADING STRUCTURE:\n")
    
    if heading_index != -1:
        # Extract everything after the HEADING STRUCTURE marker
        headings_section = content[heading_index + len("HEADING STRUCTURE:\n"):]
        
        # Split by individual lines and filter empty lines
        all_lines = headings_section.split('\n')
        heading_list = []
        
        for line in all_lines:
            line = line.strip()
            # Check if it's a heading (starts with # or H1-H6:)
            if line and (line.startswith('#') or re.match(r'^H[1-6]:', line)):
                heading_list.append(line)
        
        if st.session_state.get('debug_mode', False):
            print(f"Extracted {len(heading_list)} headings from HEADING STRUCTURE section: {heading_list}")
        
        return heading_list
    
    # Fallback patterns if HEADING STRUCTURE section isn't found
    heading_lines = re.findall(r'^(#{1,6}\s+.+?)$', content, re.MULTILINE)
    if heading_lines:
        if st.session_state.get('debug_mode', False):
            print(f"Extracted {len(heading_lines)} markdown headings: {heading_lines}")
        return heading_lines
    
    # Last resort for H1, H2, etc. format
    heading_lines = re.findall(r'^(H[1-6]:\s+.+?)$', content, re.MULTILINE)
    if heading_lines:
        if st.session_state.get('debug_mode', False):
            print(f"Extracted {len(heading_lines)} H1-H6 format headings: {heading_lines}")
        return heading_lines
    
    # If we get here, no headings were found
    if st.session_state.get('debug_mode', False):
        print("WARNING: No headings found in content!")
    return []

def extract_and_save_headings(response):
    """
    Extract headings from the response and explicitly save them to session state.
    This ensures headings are available in the edit headings section.
    """
    # Check if response has headings OR heading_structure
    has_headings = False
    
    # Create meta_and_headings if it doesn't exist
    if "meta_and_headings" not in st.session_state:
        st.session_state.meta_and_headings = {}
    
    # --- Debug: Print the entire raw API JSON response before any parsing ---
    import json
    print("\n[DEBUG] FULL RAW API RESPONSE:\n", json.dumps(response, indent=2, ensure_ascii=False))
    
    # First, check if we have the raw content from the API
    if "content" in response:
        content = response["content"]
        
        # Use your new approach to extract headings
        heading_index = content.find("HEADING STRUCTURE:\n")
        
        if heading_index != -1:
            # Extract everything after the HEADING STRUCTURE marker
            headings_section = content[heading_index + len("HEADING STRUCTURE:\n"):]
            
            # Split by double newlines and filter out empty items
            heading_list = [item for item in re.split(r"\n", headings_section) if item]
            
            print(f"\n==== EXTRACTED {len(heading_list)} HEADINGS FROM CONTENT ====")
            for i, h in enumerate(heading_list):
                print(f"{i+1}. {h}")
            
            if heading_list:
                st.session_state.meta_and_headings["headings"] = heading_list
                has_headings = True
                
                # Parse headings for the editor
                parsed = []
                for h in heading_list:
                    h = h.strip()
                    if not h:
                        continue
                    # Use regex to match any heading level (H1-H6)
                    if re.match(r'^#{1,6}\s+', h):
                        # Extract the heading level (number of # characters)
                        level = len(re.match(r'^(#+)', h).group(1))
                        # Extract the heading text (everything after the #s)
                        text = re.sub(r'^#+\s*[:.\-]?\s*', "", h).strip()
                    else:
                        m = re.match(r'^H(\d)\s*[:.\-]?\s*(.*)', h)
                        if m:
                            level = int(m.group(1))
                            text = m.group(2).strip()
                        else:
                            level = 2
                            text = h.strip()
                    parsed.append({"level": level, "text": text})
                
                if not parsed:
                    parsed.append({"level": 1, "text": "Main Heading"})
                
                st.session_state.editable_headings = parsed
    
    # Only check for already processed headings list if we didn't find them in content
    if not has_headings and "headings" in response and response["headings"]:
        st.session_state.meta_and_headings["headings"] = response["headings"]
        has_headings = True
        
        # Parse headings for the editor
        parsed = []
        lines = []
        for entry in response["headings"]:
            if isinstance(entry, str):
                lines.extend(entry.splitlines())
        
        # Now parse each line for headings
        for h in lines:
            h = h.strip()
            if not h:
                continue
            # Use regex to match any heading level (H1-H6)
            if re.match(r'^#{1,6}\s+', h):
                # Extract the heading level (number of # characters)
                level = len(re.match(r'^(#+)', h).group(1))
                # Extract the heading text (everything after the #s)
                text = re.sub(r'^#+\s*[:.\-]?\s*', "", h).strip()
            else:
                m = re.match(r'^H(\d)\s*[:.\-]?\s*(.*)', h)
                if m:
                    level = int(m.group(1))
                    text = m.group(2).strip()
                else:
                    level = 2
                    text = h.strip()
            parsed.append({"level": level, "text": text})
        
        if not parsed:
            parsed.append({"level": 1, "text": "Main Heading"})
        
        st.session_state.editable_headings = parsed
    
    # Save meta title and description if available
    if "meta_title" in response and response["meta_title"]:
        st.session_state.meta_and_headings["meta_title"] = response["meta_title"]
    
    if "meta_description" in response and response["meta_description"]:
        st.session_state.meta_and_headings["meta_description"] = response["meta_description"]
    
    # Save token usage if available
    if "token_usage" in response:
        st.session_state.meta_and_headings["token_usage"] = response["token_usage"]
    
    # Log the headings for debugging
    if has_headings and st.session_state.get('debug_mode', False):
        headings = st.session_state.meta_and_headings.get("headings", [])
        logger.debug(f"Saved {len(headings)} headings to session state")
    
    return st.session_state.get("meta_and_headings", {})

# Ensure all expected session state keys exist
if "business_data" not in st.session_state:
    st.session_state["business_data"] = ""
logger = get_logger(__name__)

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl.styles.stylesheet")

# ==== DEV MODE CONFIGURATION ====
DEV_MODE = False  # Set to True to enable dev mode
# ===============================

# Streamlit page configuration
st.set_page_config(
    page_title="SEO Content Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.extremelycoolapp.com/help',
        'Report a bug': "https://www.extremelycoolapp.com/bug",
        'About': "# SEO Content Generator\nThis app helps you generate SEO-optimized content based on CORA report data."
    }
)

# Call at the start of the app
initialize_session_state()

# Add CSS to make index column fit content
st.markdown("""
<style>
    .row_heading.level0 {width: auto !important; white-space: nowrap;}
    .blank {width: auto !important; white-space: nowrap;}
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("SEO Content Generator 2025")

# Main app title and description
st.title("SEO Content Generator")
st.markdown("""
This application generates SEO-optimized content based on CORA report data. 
Upload your CORA report, adjust heading requirements, and click 'Generate Content'.
""")

# Sidebar for API configuration
with st.sidebar:
    st.title("Configuration")
    # Simple dev mode indicator and functionality
    if DEV_MODE:
        st.info("🛠️ Development Mode Enabled", icon="🛠️")
        # Create a completely separate dev mode section that doesn't interfere with main app
        dev_step = st.selectbox(
            "Jump to step:", 
            ["1. Upload CORA Report", "2. Configure Requirements", "3. Generate Meta & Headings", "4. Generate Content", "5. View Results"]
        )
        if st.button("Load Sample Data & Go to Selected Step"):
            step_num = int(dev_step.split(".")[0])
            if step_num >= 2:
                st.session_state.file = "dummy_file"
                legacy_req = {
                    "primary_keyword": "Roof Replacement Garden Grove",
                    "variations": ["roof replacement in Garden Grove", "Garden Grove roof replacement"],
                    "lsi_keywords": {"roofing": {"count": 3}, "contractor": {"count": 2}},
                    "entities": ["Garden Grove", "Orange County"],
                    "word_count": 1500,
                    "Number of H2 tags": 5,
                    "Number of H3 tags": 8,
                    "Number of H4 tags": 12,
                    "Number of H5 tags": 0,
                    "Number of H6 tags": 1,
                    "Number of heading tags": 11,
                    "Number of Images": 2
                }
                st.session_state.requirements = legacy_req
                st.session_state.req_obj = SEORequirements(
                    primary_keyword=legacy_req["primary_keyword"],
                    variations=legacy_req["variations"],
                    lsi_keywords=legacy_req["lsi_keywords"],
                    entities=legacy_req["entities"],
                )
                st.session_state.primary_keyword = st.session_state.req_obj.primary_keyword
                st.session_state.variations = st.session_state.req_obj.variations
                st.session_state.lsi_keywords = st.session_state.req_obj.lsi_keywords
                st.session_state.entities = st.session_state.req_obj.entities
            if step_num >= 3:
                st.session_state.meta_and_headings = {
                    "meta_title": "Roof Replacement Garden Grove | Professional Roofing Services",
                    "meta_description": "Expert roof replacement services in Garden Grove. Get durable, quality roofing with our professional team. Free estimates & competitive pricing!",
                    "headings": ["H1: Professional Roof Replacement Services in Garden Grove", 
                               "H2: Why Choose Our Garden Grove Roof Replacement Services", 
                               "H2: Our Roof Replacement Process",
                               "H3: Initial Roof Inspection"]
                }
            if step_num >= 5:
                try:
                    file_path = "seo_content_roof_replacement_garden_grove.md"
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        st.session_state.generated_markdown = content
                        st.session_state.generated_html = markdown_to_html(content)
                        st.session_state.images_required = 2
                        st.session_state.analysis = {
                            "primary_keyword": "Roof Replacement Garden Grove",
                            "primary_keyword_count": 15,
                            "word_count": 1500,
                            "h1_count": 1,
                            "h2_count": 5,
                            "h3_count": 8,
                            "h4_count": 12,
                            "h5_count": 0,
                            "h6_count": 1,
                            "lsi_keywords": {"roofing": {"count": 8}, "installation": {"count": 10}, "warranty": {"count": 6}}
                        }
                except FileNotFoundError:
                    st.warning("Development markdown file not found. Using placeholder content instead.")
                    st.session_state.generated_markdown = "# Professional Roof Replacement Services in Garden Grove\n\nSample development content."
                    st.session_state.generated_html = "<h1>Professional Roof Replacement Services in Garden Grove</h1><p>Sample development content.</p>"
                    st.session_state.images_required = 2
            st.session_state.step = step_num
            st.rerun()

    anthropic_api_key = st.text_input(
        "Anthropic API Key", 
        value="",
        type="password",
        help="Enter your Anthropic API key. This will not be stored permanently."
    )
    st.session_state['anthropic_api_key'] = anthropic_api_key
    
    # Update the settings dictionary with the API key
    if 'settings' in st.session_state:
        st.session_state.settings['anthropic_api_key'] = anthropic_api_key
    
    if not anthropic_api_key:
        st.warning("Please enter your Anthropic API key to use this app.")
    
    if 'content_token_usage' in st.session_state or 'heading_token_usage' in st.session_state:
        heading_cost = 0
        if 'heading_token_usage' in st.session_state:
            heading_token_usage = st.session_state['heading_token_usage']
            # Ensure it's a dictionary
            if not isinstance(heading_token_usage, dict):
                heading_token_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
                st.session_state['heading_token_usage'] = heading_token_usage
            heading_cost = display_token_usage("Meta & Headings", heading_token_usage)
        
        content_cost = 0
        if 'content_token_usage' in st.session_state:
            content_token_usage = st.session_state['content_token_usage']
            # Ensure it's a dictionary
            if not isinstance(content_token_usage, dict):
                content_token_usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
                st.session_state['content_token_usage'] = content_token_usage
            content_cost = display_token_usage("Content Generation", content_token_usage)
        
        if 'content_token_usage' in st.session_state and 'heading_token_usage' in st.session_state:
            combined_total_cost = content_cost + heading_cost
            st.sidebar.markdown("### Combined Total Cost")
            st.sidebar.metric("Total Article Cost", f"${combined_total_cost:.4f}")
def process_upload():
    try:
        file = st.session_state.get('file', None)
        if not file:
            st.error("No file uploaded. Please upload a CORA report.")
            return
        
        # Get all data as a single dictionary
        parsed_obj = parse_cora_report(file)
        # Store the SEORequirements object
        st.session_state.req_obj = parsed_obj
        # For backward compatibility
        st.session_state.requirements = parsed_obj.to_dict()
        # Keep commonly accessed fields in session_state for legacy components
        st.session_state.primary_keyword = parsed_obj.primary_keyword
        st.session_state.variations = parsed_obj.variations
        st.session_state.lsi_keywords = parsed_obj.lsi_keywords
        st.session_state.entities = parsed_obj.entities
        st.session_state.basic_tunings = parsed_obj.basic_tunings
        # Keep the word count easily accessible 
        st.session_state.word_count = parsed_obj.word_count
        print("Basic Tunings:")
        print(st.session_state.basic_tunings)
        # Move to the next step
        st.session_state['step'] = 2
        st.success("SEO requirements extracted successfully!")

        st.rerun()
    except Exception as e:
        st.error(f"Error extracting requirements: {str(e)}")
        import traceback
        st.text_area("Error Details", traceback.format_exc(), height=300)

# File upload section
uploaded_file = st.file_uploader("Upload CORA report", type=["xlsx", "xls"])

if uploaded_file is not None:
    st.session_state['file'] = uploaded_file
    st.success(f"Successfully uploaded: {uploaded_file.name}")
    
    if st.button("Extract Requirements"):
        process_upload()
# Always show this once requirements exist
if "requirements" in st.session_state and st.session_state.requirements:
    st.markdown("### Add Business Information (Optional)")
    business_data_input = st.text_area(
        "Business Info (e.g., name, location, specialties, offers, years in business)",
        value=st.session_state.get("business_data", ""),
        height=120,
        help="This info will guide the AI before generating meta and headings."
    )

    # Only update if changed
    if business_data_input != st.session_state.get("business_data", ""):
        st.session_state.business_data = business_data_input


else:
    st.info("Please upload a CORA report to get started.")

# Add this at the module level (before generate_content_flow function)


def render_extracted_data():
    """
    Displays a persistent expander titled 'View Complete Extracted Data'
    showing the extracted SEO requirements in tables. If configured settings
    exist (headings in Step 2 or word count in Step 3), they are appended.
    """
    # Inside the render_extracted_data function in new 97.txt

    def display_dataframe(title, data, key_prefix):
        """Helper function to consistently display dataframes with a title"""
        st.write(f"**{title}:**")
        if data:
            df = pd.DataFrame(data)

            # --- Add this check and conversion ---
            if 'Value' in df.columns:
                # Convert the entire 'Value' column to string type
                # to handle mixed int/str data before Arrow conversion.
                df['Value'] = df['Value'].astype(str)
            # --- End of addition ---

            st.dataframe(df, use_container_width=True, height=200, hide_index=True)
        else:
            st.write(f"**{title}:** None")
    
    requirements = st.session_state.get("requirements", {})
    primary_keyword = st.session_state.get("primary_keyword") or requirements.get("primary_keyword", "Not found")
    variations = st.session_state.get("variations") or requirements.get("variations", [])
    lsi_keywords = st.session_state.get("lsi_keywords") or requirements.get("lsi_keywords", {})
    entities = st.session_state.get("entities") or requirements.get("entities", [])
    
    with st.expander("View Complete Extracted Data", expanded=True):
        st.markdown("### Extracted Requirements")
        st.write(f"**Primary Keyword:** {primary_keyword}")
        # Get word count from basic_tunings or requirements
        st.write(f"**Word Count Target:** {st.session_state.get('basic_tunings', {}).get('Word Count', requirements.get('word_count', 'N/A'))} words") 
        
        # Variations
        st.write(f"**Number of Keyword Variations:** {len(variations)}")
        display_dataframe("Keyword Variations", [{"Variation": v} for v in variations], "variations")

        # LSI Keywords Display
        lsi_count = len(lsi_keywords) if isinstance(lsi_keywords, dict) else len(lsi_keywords)
        st.write(f"**Number of LSI Keywords:** {lsi_count}")
        if isinstance(lsi_keywords, dict):
            lsi_data = [{"Keyword": k, "Frequency": v} for k, v in lsi_keywords.items()]
        else:
            lsi_data = [{"Keyword": k} for k in lsi_keywords]
        display_dataframe("LSI Keywords", lsi_data, "lsi")
        
        # Entities Display
        st.write(f"**Number of Entities:** {len(entities)}")
        display_dataframe("Entities", [{"Entity": e} for e in entities], "entities")
        
        # Add custom entities input
        st.subheader("Custom Entities")
        st.markdown("Add your own entities that will be prioritized at the top of the entities list")
        
        

        # Initialize custom entities in session state if it doesn't exist
        if 'custom_entities' not in st.session_state:
            st.session_state.custom_entities = []
        
        # Text area for new entities (one per line or comma-separated)
        new_entities = st.text_area(
            "Enter custom entities (one per line or comma-separated)",
            height=100,
            help="Enter entities one per line or separate them with commas. These will be prioritized in content generation."
        )
        
        col1, col2 = st.columns([1, 1])
        with col1:
            # Button to add the entities
            if st.button("Add Custom Entities"):
                if new_entities:
                    # Process the input to handle both newlines and commas
                    # First split by newlines
                    lines = [line.strip() for line in new_entities.split('\n')]
                    entity_list = []
                    
                    # Process each line - if it contains commas, split further
                    for line in lines:
                        if line:  # Skip empty lines
                            if ',' in line:
                                # Split by comma and add each item
                                comma_entities = [e.strip() for e in line.split(',') if e.strip()]
                                entity_list.extend(comma_entities)
                            else:
                                # Add the whole line as one entity
                                entity_list.append(line)
                    
                    # Save to session state
                    st.session_state.custom_entities = entity_list
                    
                    # Update the requirements dictionary
                    if isinstance(st.session_state.requirements, dict):
                        # Save custom entities separately
                        st.session_state.requirements['custom_entities'] = entity_list
                        
                        # Get the current entities list
                        current_entities = st.session_state.requirements.get('entities', [])
                        
                        # Add new custom entities to the entities list (avoiding duplicates)
                        for entity in entity_list:
                            if entity not in current_entities:
                                current_entities.append(entity)
                        
                        # Update the entities list
                        st.session_state.requirements['entities'] = current_entities
                        st.session_state.entities = current_entities
                    
                    st.success(f"Added {len(entity_list)} custom entities!")
                    # Rerun to show updated entities
                    st.rerun()
        
        with col2:
            # Button to clear custom entities
            if st.button("Clear Custom Entities"):
                if 'custom_entities' in st.session_state and st.session_state.custom_entities:
                    # Save the custom entities to remove BEFORE clearing the list
                    custom_entities_to_remove = list(st.session_state.custom_entities)
                    
                    # Clear from session state
                    st.session_state.custom_entities = []
                    
                    # Update the requirements dictionary
                    if isinstance(st.session_state.requirements, dict):
                        # Clear custom entities
                        st.session_state.requirements['custom_entities'] = []
                        
                        # Get the current entities list
                        current_entities = st.session_state.requirements.get('entities', [])
                        
                        # Remove custom entities from the entities list
                        for entity in custom_entities_to_remove:
                            if entity in current_entities:
                                current_entities.remove(entity)
                        
                        # Update the entities list
                        st.session_state.requirements['entities'] = current_entities
                        st.session_state.entities = current_entities
                    
                    st.success("Custom entities cleared!")
                    # Rerun to show updated entities
                    st.rerun()
        
        # Display current custom entities
        if st.session_state.custom_entities:
            st.markdown("**Current Custom Entities:**")
            custom_ent_df = pd.DataFrame({"Entity": st.session_state.custom_entities})
            st.dataframe(custom_ent_df, use_container_width=True, height=200, hide_index=True)
        
        if requirements:
            # Expanded list of excluded keys for roadmap requirements
            excluded_keys = [
                "primary_keyword", "variations", "lsi_keywords", 
                "entities", "custom_entities", "word_count", "images",
                "Number of heading tags", "Number of H1 tags", "Number of H2 tags",
                "Number of H3 tags", "Number of H4 tags", "Number of H5 tags",
                "Number of H6 tags"
            ]
            
            roadmap_data = []

            # First add any top-level requirements
            for k, v in requirements['roadmap_requirements'].items():
                # Skip if in excluded list, is a complex data structure, or is a known nested dictionary
                if (k in excluded_keys or 
                    k.startswith("Number of H") or  # This will catch any heading tag pattern
                    isinstance(v, (dict, list)) and not isinstance(v, (int, str, bool, float)) or
                    k in ["requirements", "basic_tunings", "heading_structure", "debug_info", "heading_overrides"]):
                    continue
                roadmap_data.append({"Requirement": k, "Value": v})
            
            # Then look for nested requirements if they exist
            if "requirements" in requirements and isinstance(requirements["requirements"], dict):
                nested_reqs = requirements["requirements"]
                for k, v in nested_reqs.items():
                    if (k not in excluded_keys and 
                        not k.startswith("Number of H") and  # This will catch any heading tag pattern 
                        (not isinstance(v, (dict, list)) or isinstance(v, (int, str, bool, float)))):
                        roadmap_data.append({"Requirement": k, "Value": v})
            
            # Display the combined roadmap data
            display_dataframe("Roadmap Requirements", roadmap_data, "roadmap")



        # Configured Settings for Headings (Step 2)
        if "configured_headings" in st.session_state:
            configured_headings = st.session_state["configured_headings"]
            st.markdown("### Configured Settings (Headings)")
            st.write(f"H1 Headings: {configured_headings.get('h1', 'N/A')}")
            st.write(f"H2 Headings: {configured_headings.get('h2', 'N/A')}")
            st.write(f"H3 Headings: {configured_headings.get('h3', 'N/A')}")
            st.write(f"H4 Headings: {configured_headings.get('h4', 'N/A')}")
            st.write(f"H5 Headings: {configured_headings.get('h5', 'N/A')}")
            st.write(f"H6 Headings: {configured_headings.get('h6', 'N/A')}")
            # Use the total calculated and stored during configuration
            configured_total = configured_headings.get('total', 'N/A')
            # Use the total calculated and stored during configuration in Step 2
            configured_total = configured_headings.get('total', 'N/A')
            st.write(f"Total Headings: {configured_total}")
        
# Generate content flow
def generate_content_flow():
    """Generate and display content."""
    requirements = st.session_state.requirements  # This is what you're missing
    # Only proceed if we have requirements and meta/headings
    if 'requirements' not in st.session_state or not st.session_state.requirements:
        st.error("No requirements data found. Please upload a CORA report first.")
    
    if 'meta_and_headings' not in st.session_state or not st.session_state.meta_and_headings:
        st.error("No meta and headings data found. Please generate meta and headings first.")
    
    # Check for existing content
    if 'generated_markdown' in st.session_state and st.session_state.generated_markdown and not st.session_state.get('auto_generate_content', False):
        # Display existing content
        display_generated_content()
        
        # Add regenerate button
        if st.button("Regenerate Content"):
            st.session_state['auto_generate_content'] = True
            st.rerun()
        
    # Only show Heading Structure Configuration in Step 2, not in Step 2.5
    if st.session_state.get("step", 1) == 2:
        #content_placeholder, status_placeholder, thinking_placeholder = stream_content_display()

        # Display target word count (set earlier in Step 2.5)
        word_count = st.session_state.requirements.get("word_count", 1500)
        st.metric("Target Word Count", word_count)
        
        # Heading Structure Configuration
        st.subheader("Heading Structure Configuration")
        st.markdown("Configure the number of headings for the generated content. Total headings will update automatically.")
        
        # Create columns
        # Inside Step 2 (around line 450)
        basic_tunings = st.session_state.get('basic_tunings', {})
        # Get default heading values FROM basic_tunings
        default_h1 = basic_tunings.get("Number of H1 tags", 1) # Assuming key is "Number of H1 tags"
        default_h2 = basic_tunings.get("Number of H2 tags", 4) # Adjust key name if different
        default_h3 = basic_tunings.get("Number of H3 tags", 8) # Adjust key name if different
        default_h4 = basic_tunings.get("Number of H4 tags", 0) # Adjust key name if different
        default_h5 = basic_tunings.get("Number of H5 tags", 0) # Adjust key name if different
        default_h6 = basic_tunings.get("Number of H6 tags", 0) # Adjust key name if different


        h1_col, h2_col, h3_col, h4_col, h5_col, h6_col, total_col = st.columns(7)

        with h1_col:
            h1_count = st.number_input("H1 Headings", min_value=0, max_value=100, value=int(default_h1), key='h1_config')
            st.session_state.requirements["Number of H1 tags"] = h1_count

        with h2_col:
            h2_count = st.number_input("H2 Headings", min_value=0, max_value=100, value=int(default_h2), key='h2_config')
            st.session_state.requirements["Number of H2 tags"] = h2_count

        with h3_col:
            h3_count = st.number_input("H3 Headings", min_value=0, max_value=100, value=int(default_h3), key='h3_config')
            st.session_state.requirements["Number of H3 tags"] = h3_count

        with h4_col:
            h4_count = st.number_input("H4 Headings", min_value=0, max_value=100, value=int(default_h4), key='h4_config')
            st.session_state.requirements["Number of H4 tags"] = h4_count

        with h5_col:
            h5_count = st.number_input("H5 Headings", min_value=0, max_value=100, value=int(default_h5), key='h5_config')
            st.session_state.requirements["Number of H5 tags"] = h5_count

        with h6_col:
            h6_count = st.number_input("H6 Headings", min_value=0, max_value=100, value=int(default_h6), key='h6_config')
            st.session_state.requirements["Number of H6 tags"] = h6_count

        # Calculate total headings (sum of H1-H6)
        total_headings = h1_count + h2_count + h3_count + h4_count + h5_count + h6_count
        st.metric("Total Headings", total_headings, help="Total count of headings (H1 + H2 + H3 + H4 + H5 + H6).")
        # Store the total in requirements
        requirements["Number of heading tags"] = total_headings
        
        # Save the updated requirements back to session state
        st.session_state.requirements = requirements
    

 
# Generate full content button function
def generate_full_content_button():
    """Function to handle the Generate Full Content button."""
    st.session_state.step = 3
    st.session_state.auto_generate_content = True

# Main application flow based on current step
if st.session_state.get("step", 1) == 1:
    # Step 1: Upload CORA report (already handled above)
    pass

# In the main application flow section
elif st.session_state.get("step", 1) == 2:
    # Clear any previously generated content when entering step 2
    # This prevents content from a previous run persisting
    # clear any stale content
    st.session_state.generated_markdown = ""
    st.session_state.generated_html = ""
    
    # Step 2: Configure Requirements and Generate Meta/Headings
    requirements = dict(st.session_state.requirements)
    requirements.update(requirements.get("basic_tunings", {}))
    requirements.update(requirements.get("roadmap_requirements", {}))

    render_extracted_data()
    primary_keyword = st.session_state.get("primary_keyword", "Not found") 
    st.subheader("Configure Heading Requirements")
    
    # Heading configuration - ONLY SHOW HERE IN STEP 2
    default_h1 = int(requirements.get("Number of H1 tags", 1))
    default_h2 = int(requirements.get("Number of H2 tags", 0))
    default_h3 = int(requirements.get("Number of H3 tags", 0))
    default_h4 = int(requirements.get("Number of H4 tags", 0))
    default_h5 = int(requirements.get("Number of H5 tags", 0))
    default_h6 = int(requirements.get("Number of H6 tags", 0))
    
    # Create heading input grid
    st.markdown("Adjust the number of headings for each level:")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        h1_count = st.number_input("H1 Headings", min_value=0, max_value=100, value=default_h1, key='h1_config')
    with col2:
        h2_count = st.number_input("H2 Headings", min_value=0, max_value=100, value=default_h2, key='h2_config')
    with col3:
        h3_count = st.number_input("H3 Headings", min_value=0, max_value=100, value=default_h3, key='h3_config')
    with col4:
        h4_count = st.number_input("H4 Headings", min_value=0, max_value=100, value=default_h4, key='h4_config')
    
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        h5_count = st.number_input("H5 Headings", min_value=0, max_value=100, value=default_h5, key='h5_config')
    with col6:
        h6_count = st.number_input("H6 Headings", min_value=0, max_value=100, value=default_h6, key='h6_config')
    
    total_headings = h1_count + h2_count + h3_count + h4_count + h5_count + h6_count
    
    with col7:
        st.metric("Total Headings", total_headings)
    
    st.session_state.configured_headings = {
        "h1": h1_count,
        "h2": h2_count,
        "h3": h3_count,
        "h4": h4_count,
        "h5": h5_count,
        "h6": h6_count,
        "total": total_headings
    }
    
    # Update requirements with the configured heading counts
    for h_level, count in zip(range(1, 7), [h1_count, h2_count, h3_count, h4_count, h5_count, h6_count]):
        st.session_state.requirements[f"Number of H{h_level} tags"] = count
    st.session_state.requirements["Number of heading tags"] = total_headings
    
    # Generate button
    col1, col2 = st.columns(2)
    with col1:
        generate_button = st.button("Generate Meta Title, Description and Headings", use_container_width=True)

    
    if generate_button:
        try:
            if not st.session_state.get('anthropic_api_key', ''):
                st.error("Please enter your Anthropic API key in the sidebar.")
            else:
                content_placeholder, status_placeholder, thinking_placeholder = stream_content_display()
                status_placeholder.info("Connecting to AI and generating content…")

                # reset accumulators
                accumulated_content = [""]
                st.session_state.accumulated_thinking = ""

                # 2) define streaming callback
                def update_stream(content=None, thinking_content=None):
                    if content:
                        accumulated_content[0] += content
                        st.session_state.generated_markdown = accumulated_content[0]
                        html_content = accumulated_content[0].replace('\n', '<br>')
                        html = f"""
                        <div class="content-container">
                            {html_content}
                        </div>
                        """
                        content_placeholder.markdown(html, unsafe_allow_html=True)
                        
                        # NO EXTRACTION HERE - we only display the content
                    
                    if thinking_content is not None:
                        # Just accumulate thinking content
                        st.session_state.accumulated_thinking += thinking_content
                        thinking_placeholder.markdown(f"<div class='thinking-container'>{st.session_state.accumulated_thinking}</div>", unsafe_allow_html=True)
                
                # 3) MAKE THE SINGLE API CALL
                response = generate_meta_and_headings(
                    st.session_state.requirements,
                    st.session_state.settings,
                    st.session_state.business_data,
                    stream=True,
                    stream_callback=update_stream
                )

                # Debug raw response before any parsing or session state modification
                print(json.dumps(response, indent=4))
                
                # Now streaming is complete, let's extract everything from the full content
                print(f"\nSTREAMING COMPLETED — {len(accumulated_content[0])} chars")
                
                # Step 1: Extract meta information
                meta_title_pattern = r"META TITLE:\s*(.*?)(?:\n|$)"
                meta_desc_pattern = r"META DESCRIPTION:\s*(.*?)(?:\n|$)"
                heading_pattern = r"HEADING STRUCTURE:(.*?)(?=\n\n|$)"
                
                meta_title_match = re.search(meta_title_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                meta_desc_match = re.search(meta_desc_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                heading_match = re.search(heading_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                
                # Step 2: Update response dict (ensure response["headings"] is populated)
                if meta_title_match:
                    response["meta_title"] = meta_title_match.group(1).strip()
                
                if meta_desc_match:
                    response["meta_description"] = meta_desc_match.group(1).strip()
                
                # CRUCIAL: Extract headings from full accumulated content
                if heading_match:
                    heading_text = heading_match.group(1).strip()
                    # Replace with this (matches any heading level H1-H6):
                    heading_lines = extract_headings_from_content(accumulated_content[0])
                    print(f"EXTRACTED {len(heading_lines)} markdown headings from HEADING STRUCTURE section")
                    for h in heading_lines:
                        print(f"  - {h}")
                    response["headings"] = heading_lines
                else:
                    # If no HEADING STRUCTURE section, try other extraction methods
                    all_extracted_headings = extract_headings_from_content(accumulated_content[0])
                    if all_extracted_headings:
                        print(f"EXTRACTED {len(all_extracted_headings)} HEADINGS VIA FALLBACK")
                        for h in all_extracted_headings:
                            print(f"  - {h}")
                        response["headings"] = all_extracted_headings
                    else:
                        print("WARNING: No headings found, using default heading")
                        response["headings"] = [f"# {st.session_state.primary_keyword}"]
                
                # Step 3: Explicitly update session state with extracted data
                if "meta_and_headings" not in st.session_state:
                    st.session_state.meta_and_headings = {}
                
                # Explicitly set headings in session state
                if "headings" in response:
                    st.session_state.meta_and_headings["headings"] = response["headings"]
                    print(f"SAVED {len(response['headings'])} HEADINGS TO SESSION STATE")
                
                # Also save other meta information
                if "meta_title" in response:
                    st.session_state.meta_and_headings["meta_title"] = response["meta_title"]
                    st.session_state["meta_title_input"] = response["meta_title"]
                if "meta_description" in response:
                    st.session_state.meta_and_headings["meta_description"] = response["meta_description"]
                    st.session_state["meta_desc_input"] = response["meta_description"]
                if "token_usage" in response:
                    st.session_state.meta_and_headings["token_usage"] = response["token_usage"]
                
                # Step 4: Call extract_and_save_headings ONCE after everything is set up
                if "headings" in response and response["headings"]:
                    extract_and_save_headings(response)
                
                # Save thinking process for reference
                if 'accumulated_thinking' in st.session_state:
                    st.session_state.headings_thinking_process = st.session_state.accumulated_thinking
                
                # 5) Advance to the next sub‐step automatically:
                st.session_state.step = 2.5
                status_placeholder.success("Generation complete!")
                st.rerun()
        except Exception as e:
            st.error(f"Error generating meta information and headings: {e}")
            import traceback
            st.text_area("Error Details", traceback.format_exc(), height=300)
            st.warning("To retry, click the button again.")
            # Immediately call the function to execute in the correct scope (outside the function)
            response = run_generation()
            
            st.session_state.meta_and_headings = {
                "meta_title": response.get("meta_title", ""),
                "meta_description": response.get("meta_description", ""),
                "headings": response.get("headings", []),
                "token_usage": response.get("token_usage", {})
            }
            
            # Update the session state after the heading generation
            if "headings" in response:
                # Ensure meta_and_headings exists
                if "meta_and_headings" not in st.session_state:
                    st.session_state.meta_and_headings = {}
                
                # Store the headings in the meta_and_headings object explicitly
                st.session_state.meta_and_headings["headings"] = response["headings"]
                # Also store other meta information
                if "meta_title" in response:
                    st.session_state.meta_and_headings["meta_title"] = response["meta_title"]
                if "meta_description" in response:
                    st.session_state.meta_and_headings["meta_description"] = response["meta_description"]
                if "token_usage" in response:
                    st.session_state.meta_and_headings["token_usage"] = response["token_usage"]
            
            # Store the thinking process for future reference
            if 'accumulated_thinking' in st.session_state:
                st.session_state.headings_thinking_process = st.session_state.accumulated_thinking
                
            # Add a debug expander to keep thinking process visible
            with st.expander("Debug - Headings Thinking Process", expanded=False):
                if 'accumulated_thinking' in st.session_state:
                    st.markdown(
                        """
                        <div class="content-container">
                        {content}
                        </div>
                        """.format(content=st.session_state.accumulated_thinking.replace('\n', '<br>')),
                        unsafe_allow_html=True
                    )
            
            # Store original values for reset functionality
            st.session_state['original_meta_and_headings'] = dict(st.session_state.meta_and_headings)
            st.session_state['original_requirements'] = dict(st.session_state.requirements)
            
            # Move to heading editing step - this is crucial!
            st.session_state['step'] = 2.5
            
            # Make sure the thinking process is preserved when moving from step 2 to 2.5
            if 'accumulated_thinking' in st.session_state:
                # Create a longer-lived variable to preserve thinking process between steps
                st.session_state['persistent_thinking_process'] = st.session_state.get('accumulated_thinking', '')
                # Log that we're preserving it
                print(f"Preserving thinking process ({len(st.session_state['persistent_thinking_process'])} chars) for step 2.5")
            
            # Clear any previously generated content and thinking
            if 'generated_markdown' in st.session_state:
                st.session_state.generated_markdown = ''
            if 'generated_html' in st.session_state:
                st.session_state.generated_html = ''
            
            # Track token usage
            st.session_state['heading_token_usage'] = response.get("token_usage", {})
            
            status_placeholder.success("Generation complete!")
            st.session_state.step = 2.5
            st.rerun()

        except Exception as e:
            st.error(f"Error generating meta information and headings: {str(e)}")
            import traceback
            st.text_area("Error Details", traceback.format_exc(), height=300)
            st.warning("To retry, please click the 'Generate Meta Title...' button again.")
    
elif st.session_state.get("step", 1) == 2.5:

    # flattened copy for convenience
    requirements = dict(st.session_state.requirements)
    
    requirements.update(requirements.get("basic_tunings", {}))
    requirements.update(requirements.get("roadmap_requirements", {}))
 
    st.subheader("Step 2.5: Review and Edit Meta & Headings")
    
    # Display the preserved thinking process from step 2 if available
    with st.expander("Debug - Headings Generation Thinking Process", expanded=False):
        if 'persistent_thinking_process' in st.session_state and st.session_state['persistent_thinking_process']:
            st.markdown(
                """
                <div class="content-container">
                {content}
                </div>
                """.format(content=st.session_state['persistent_thinking_process'].replace('\n', '<br>')),
                unsafe_allow_html=True
            )
            print(f"Displaying preserved thinking process from step 2 ({len(st.session_state['persistent_thinking_process'])} chars)")
        elif 'headings_thinking_process' in st.session_state:
            st.markdown(
                """
                <div class="content-container">
                {content}
                </div>
                """.format(content=st.session_state.headings_thinking_process.replace('\n', '<br>')),
                unsafe_allow_html=True
            )
        else:
            st.info("No thinking process available from headings generation.")
    
    # Debug the current meta_and_headings state
    with st.expander("Debug - Meta and Headings Data", expanded=False):
        st.write("Current meta_and_headings object:")
        st.json(st.session_state.meta_and_headings)
        
        if st.button("Load Sample Headings for Testing"):
            st.session_state.meta_and_headings = {
                "headings": [
                    "# Professional Garden Grove Roof Replacement Services",
                    "## Why Choose Our Roofing Services",
                    "## Our Comprehensive Roof Replacement Process",
                    "### Initial Roof Inspection",
                    "### Material Selection",
                    "### The Installation Process",
                    "## Benefits of Professional Roof Replacement",
                    "### Increased Home Value",
                    "### Enhanced Energy Efficiency",
                    "## Warranty and Maintenance"
                ],
                "meta_title": "Professional Roof Replacement in Garden Grove | Expert Roofing",
                "meta_description": "Get expert roof replacement in Garden Grove from certified professionals. Quality materials, excellent craftsmanship, and 25+ years of experience. Free estimates!"
            }
            st.rerun()
    
    st.markdown("### Meta Title & Description")
    
    # Meta Title with counter
    meta_title = st.text_input("Meta Title", value=st.session_state.meta_and_headings.get("meta_title", ""), key="meta_title_input")
    title_count = len(meta_title)
    title_limit = requirements.get("Title Length", 60)
    st.progress(min(1.0, title_count / title_limit))
    st.markdown(f"**Meta Title Characters:** {title_count}/{title_limit}")

    # Meta Description with counter
    meta_description = st.text_area("Meta Description", value=st.session_state.meta_and_headings.get("meta_description", ""), key="meta_desc_input", height=100)
    desc_count = len(meta_description)
    desc_limit = requirements.get("Description Length", 160)
    st.progress(min(1.0, desc_count / desc_limit))
    st.markdown(f"**Meta Description Characters:** {desc_count}/{desc_limit}")

    # ADD WORD COUNT EDITOR HERE - right after meta description
    st.markdown("### Target Word Count")
    default_word_count = st.session_state.requirements.get("word_count", 1500)
    word_count = st.number_input(
        "Target Word Count",
        min_value=300,
        max_value=5000,
        value=default_word_count,
        step=100,
        key="word_count_input_edit",  # Different key
        help="Specify the target word count for the generated content."
    )
    st.session_state.requirements["word_count"] = word_count
    
    # Add content configuration section
    st.markdown("### Content Configuration")
    st.markdown("Select optional features to enhance your content:")
    
    # Create a container for the content configuration options
    content_config_container = st.container()
    
    with content_config_container:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            use_tables = st.checkbox(
                "Use Tables", 
                value=st.session_state.get("use_tables", False),
                help="Include comparison tables where useful to present information in a structured format"
            )
            
        with col2:
            use_lists = st.checkbox(
                "Use Lists", 
                value=st.session_state.get("use_lists", False),
                help="Include bullet lists and numbered lists where appropriate to enhance content organization"
            )
            
        with col3:
            create_images = st.checkbox(
                "Create Images", 
                value=st.session_state.get("create_images", False),
                help="Add image placeholders for each H2 section with optimized filenames and alt text"
            )
    
    # Store content configuration in session state
    st.session_state.use_tables = use_tables
    st.session_state.use_lists = use_lists
    st.session_state.create_images = create_images
    
    # Redesigned heading editor section for better usability with many headings
    # More compact, modern editor with minimal whitespace
    st.markdown("### Edit Headings")
    
    # Add button to refresh headings from raw content
    # Add button to refresh headings from raw content
    if st.button("🔄 Refresh Headings from API Response", help="Re-extract headings from the full API response content"):
        # Check if we have the raw content from the API
        if "content" in st.session_state.get("meta_and_headings", {}):
            content = st.session_state.meta_and_headings["content"]
            
            # Debug output to console
            print("\n==== REFRESH HEADINGS: EXAMINING FULL CONTENT ====")
            print(f"Content length: {len(content)} characters")
            print(f"Content preview: {content[:500]}...")
            
            # Look for HEADING STRUCTURE section
            heading_pattern = r"HEADING STRUCTURE:(.*?)(?=\n\n|\Z)"
            heading_match = re.search(heading_pattern, content, re.DOTALL | re.IGNORECASE)
            
            if heading_match:
                heading_text = heading_match.group(1).strip()
                print(f"\n==== FOUND HEADING STRUCTURE SECTION ====")
                print(f"Heading text length: {len(heading_text)} characters")
                print(f"Heading text: {heading_text}")
                
                # Use the robust extraction function for ALL headings
                heading_lines = extract_headings_from_content(content)
                
                print(f"\n==== EXTRACTED HEADING LINES ====")
                for i, h in enumerate(heading_lines):
                    print(f"{i+1}. {h}")
                
                if heading_lines:
                    # Update session state with the extracted headings
                    st.session_state.meta_and_headings["headings"] = heading_lines
                    
                    # Also update editable_headings
                    parsed = []
                    for h in heading_lines:
                        if re.match(r'^#{1,6}\s+', h):
                            level = len(re.match(r'^(#+)', h).group(1))
                            text = h.lstrip('#').strip()
                            parsed.append({"level": level, "text": text})
                        else:
                            # fallback: treat as H2 if not markdown
                            parsed.append({"level": 2, "text": h})
                    st.session_state.editable_headings = parsed
                    st.success(f"Refreshed {len(heading_lines)} headings from API response.")
                else:
                    st.warning("No headings found in HEADING STRUCTURE section.")
            else:
                # fallback: try extracting from full content
                heading_lines = extract_headings_from_content(content)
                if heading_lines:
                    st.session_state.meta_and_headings["headings"] = heading_lines
                    parsed = []
                    for h in heading_lines:
                        if re.match(r'^#{1,6}\s+', h):
                            level = len(re.match(r'^(#+)', h).group(1))
                            text = h.lstrip('#').strip()
                            parsed.append({"level": level, "text": text})
                        else:
                            parsed.append({"level": 2, "text": h})
                    st.session_state.editable_headings = parsed
                    st.success(f"Refreshed {len(heading_lines)} headings from API response (fallback mode).")
                else:
                    st.warning("No headings found in API response.")

        else:
            st.warning("No content available in API response. Generate headings first.")

    # Style for ultra-compact heading editor
    st.markdown("""
    <style>
        /* Remove default padding/margins in Streamlit elements */
        .stSelectbox, .stTextInput, .stButton {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
            padding-top: 0 !important;
        }

        
        /* Smaller, inline buttons */
        .stButton>button {
            padding: 2px 5px !important;
            font-size: 11px !important;
            line-height: 1 !important;
            min-height: 0 !important;
            height: auto !important;
        }
        
        /* Reduce input padding */
        .stTextInput>div>div>input {
            padding: 2px 8px !important;
            line-height: 1.2 !important;
            font-size: 13px !important;
        }
        
        /* Style for dropdown and inputs */
        div[data-baseweb="select"] {
            min-height: 30px !important;
        }
        
        /* Compact container styling */
        .element-container {
            margin-bottom: 0 !important;
        }
        
        /* Compact pagination area */
        .pagination-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
            padding: 3px 6px;
            margin-bottom: 8px;
            border-bottom: 1px solid #ddd;
        }
        
        /* Action buttons */
        .heading-actions {
            display: flex;
            gap: 2px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Function to log headings for debugging
    def debug_headings():
        headings = st.session_state.meta_and_headings.get("headings", [])
        print(f"Original headings from meta_and_headings: {headings}")
        
        if "editable_headings" in st.session_state:
            print(f"Parsed editable headings: {st.session_state.editable_headings}")
    
    # Debug log of headings
    debug_headings()
    
    # Only initialize editable_headings from meta_and_headings if not present
    if "editable_headings" not in st.session_state:
        parsed = []
        headings = st.session_state.meta_and_headings.get("headings", [])
        # Debug: Print raw headings
        print(f"Raw headings from API: {headings}")
        # Always flatten and parse
        lines = []
        for h in headings:
            if isinstance(h, str):
                lines.extend(h.splitlines())
        for h in lines:
            h = h.strip()
            if not h:
                continue
            if re.match(r'^#{1,6}\s+', h):
                level = len(re.match(r'^(#+)', h).group(1))
                text = re.sub(r'^#+\s*[:.\-]?\s*', "", h).strip()
            else:
                m = re.match(r'^H(\d)\s*[:.\-]?\s*(.*)', h)
                if m:
                    level = int(m.group(1))
                    text = m.group(2).strip()
                else:
                    level = 2
                    text = h.strip()
            parsed.append({"level": level, "text": text})
        # Debug: Print parsed headings
        print(f"Parsed editable_headings: {parsed}")
        # If no headings were parsed, create a default one
        if not parsed:
            parsed.append({"level": 1, "text": "Main Heading"})
        st.session_state.editable_headings = parsed
    
    # Compact top controls with search and add button
    col1, col2 = st.columns([5, 1])
    with col1:
        heading_search = st.text_input("Filter", key="heading_search", placeholder="Type to filter headings...")
    with col2:
        if st.button("➕ Add Top", key="add_top", help="Add heading at top"):
            st.session_state.editable_headings.insert(0, {"level": 2, "text": "New Heading"})
            st.rerun()

    # Pagination
    headings_per_page = 15  # Show more headings per page
    if "heading_editor_page" not in st.session_state:
        st.session_state.heading_editor_page = 0

    # Filter headings
    filtered_headings = []
    for i, heading in enumerate(st.session_state.editable_headings):
        if not heading_search or heading_search.lower() in heading["text"].lower():
            filtered_headings.append((i, heading))

    # Calculate pagination info
    total_pages = max(1, len(filtered_headings) // headings_per_page + 
                    (1 if len(filtered_headings) % headings_per_page > 0 else 0))

    if filtered_headings:
        # Minimalist pagination display
        col1, col2, col3 = st.columns([1, 3, 1])
        with col1:
            if st.button("◀️", disabled=st.session_state.heading_editor_page <= 0, key="prev_page"):
                st.session_state.heading_editor_page -= 1
                st.rerun()
        with col2:
            st.markdown(f"""
            <div class="pagination-bar">
                <span>{len(filtered_headings)} headings</span>
                <span>Page {st.session_state.heading_editor_page + 1}/{total_pages}</span>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            if st.button("▶️", disabled=st.session_state.heading_editor_page >= total_pages - 1, key="next_page"):
                st.session_state.heading_editor_page += 1
                st.rerun()
        
        # Calculate slice for current page
        start_idx = st.session_state.heading_editor_page * headings_per_page
        end_idx = start_idx + headings_per_page
        current_page = filtered_headings[start_idx:end_idx]
        
        # Display headings in current page
        for idx, (orig_idx, heading) in enumerate(current_page):
            heading_id = f"heading_{orig_idx}"
            
            # Level selector, text input, and controls
            cols = st.columns([1, 6, 2])
            
            with cols[0]:
                new_level = st.selectbox(
                    "", 
                    list(range(1, 7)),
                    index=heading["level"] - 1,
                    key=f"{heading_id}_level",
                    label_visibility="collapsed"
                )
            
            with cols[1]:
                new_text = st.text_input(
                    "",
                    value=heading["text"],
                    key=f"{heading_id}_text",
                    label_visibility="collapsed"
                )
            
            with cols[2]:
                # Ultra compact actions
                action_cols = st.columns([1, 1, 1, 1, 1])
                
                with action_cols[0]:
                    if st.button("⬆️", key=f"{heading_id}_up", help="Move up"):
                        if orig_idx > 0:
                            st.session_state.editable_headings[orig_idx], st.session_state.editable_headings[orig_idx-1] = \
                            st.session_state.editable_headings[orig_idx-1], st.session_state.editable_headings[orig_idx]
                            st.rerun()
                
                with action_cols[1]:
                    if st.button("⬇️", key=f"{heading_id}_down", help="Move down"):
                        if orig_idx < len(st.session_state.editable_headings) - 1:
                            st.session_state.editable_headings[orig_idx], st.session_state.editable_headings[orig_idx+1] = \
                            st.session_state.editable_headings[orig_idx+1], st.session_state.editable_headings[orig_idx]
                            st.rerun()
                
                with action_cols[2]:
                    if st.button("+", key=f"{heading_id}_add", help="Add below"):
                        st.session_state.editable_headings.insert(orig_idx+1, {"level": heading["level"], "text": "New Heading"})
                        st.rerun()
            
                
                with action_cols[3]:
                    if st.button("🗑️", key=f"{heading_id}_delete", help="Delete"):
                        st.session_state.editable_headings.pop(orig_idx)
                        st.rerun()
        
            # Update the heading with new values
            st.session_state.editable_headings[orig_idx]["level"] = new_level
            st.session_state.editable_headings[orig_idx]["text"] = new_text
    
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Add heading at bottom button
        if st.button("➕ Add Bottom", key="add_bottom"):
            st.session_state.editable_headings.append({"level": 2, "text": "New Heading"})
            st.rerun()
    else:
        st.info("No headings match your search. Try different keywords or add a new heading.")

    # Update the headings in meta
    markdown_headings = [("#" * h['level']) + " " + h['text'] for h in st.session_state.editable_headings]
    st.session_state.meta_and_headings["headings"] = markdown_headings


    # Fixed Live Preview expander
    with st.expander("Live Preview", expanded=False):
        preview_md = "\n\n".join([("#" * h["level"]) + " " + h["text"] for h in st.session_state.editable_headings])
        st.markdown(preview_md)
    # After the heading editor, add heading count comparison
    st.markdown("---")
    st.markdown("### Heading Count Comparison")

    # Calculate current heading counts from the editable headings
    current_counts = {f"h{i}": 0 for i in range(1, 7)}
    for h in st.session_state.editable_headings:
        current_counts[f"h{h['level']}"] += 1

    # Get expected counts from requirements
    expected_counts = {
        "h1": st.session_state.requirements.get("Number of H1 tags", 1),
        "h2": st.session_state.requirements.get("Number of H2 tags", 4),
        "h3": st.session_state.requirements.get("Number of H3 tags", 8),
        "h4": st.session_state.requirements.get("Number of H4 tags", 0),
        "h5": st.session_state.requirements.get("Number of H5 tags", 0),
        "h6": st.session_state.requirements.get("Number of H6 tags", 0)
    }

    # Create comparison table
    comparison_data = []
    current_total = 0
    expected_total = 0

    for i in range(1, 7):
        h_key = f"h{i}"
        current = current_counts[h_key]
        expected = expected_counts[h_key]
        diff = current - expected
        current_total += current
        expected_total += expected
        
        status = "✅" if current == expected else "⚠️"
        comparison_data.append({
            "Heading": f"H{i}",
            "Expected": expected,
            "Current": current,
            "Difference": diff,
            "Status": status
        })

    # Add total row
    total_status = "✅" if current_total == expected_total else "⚠️"
    comparison_data.append({
        "Heading": "Total",
        "Expected": expected_total,
        "Current": current_total,
        "Difference": current_total - expected_total,
        "Status": total_status
    })

    # Display as dataframe
    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    # Show warning if counts don't match
    if current_total != expected_total:
        st.warning(f"Current heading count ({current_total}) doesn't match the expected count ({expected_total}). This may affect SEO performance.")
    with st.expander("Live Preview", expanded=False):
        preview_md = "\n\n".join([("#" * h["level"]) + " " + h["text"] for h in st.session_state.editable_headings])
        st.markdown(preview_md)

    if st.button("🚀 Generate Full SEO Content Now"):
        st.session_state.step = 3  # Set the step to 3
        st.session_state.auto_generate_content = True  # ADD THIS LINE
        st.rerun()  # This will jump to the step 3 block

   
    elif st.session_state.get('auto_generate_content', False):
        # re-run content generation flow only when explicitly requested
        generate_content_flow()
     
    

elif st.session_state.get("step", 1) == 3:
    st.subheader("Step 3: View Generated Content")
    render_extracted_data()

    # If content hasn't been generated yet, generate it
    # If content hasn't been generated yet, generate it
    if (
        'generated_markdown' not in st.session_state 
        or not st.session_state.generated_markdown 
        or st.session_state.get('force_regenerate', False) 
        or st.session_state.get('auto_generate_content', False)
    ):
        # Reset flags immediately
        st.session_state.pop('force_regenerate', None)
        st.session_state['auto_generate_content'] = False
        # Get streaming content display components
        content_placeholder, status_placeholder, thinking_placeholder = stream_content_display()
        
        with st.spinner("Preparing content generation..."):
            # Call the existing function to generate content
            # But don't show the configuration UI again
            try:
                # Prepare settings
                settings = {
                    'model': 'claude',
                    'anthropic_api_key': st.session_state.get('anthropic_api_key', ''),
                    'generate_tables': st.session_state.get('use_tables', False),
                    'generate_lists': st.session_state.get('use_lists', False),
                    'generate_images': st.session_state.get('create_images', False),
                }
                
                # Update session state settings
                st.session_state.settings = settings
                
                if not st.session_state.get('anthropic_api_key', ''):
                    st.error("Please enter your Anthropic API key in the sidebar.")
                else:
                    # Get streaming content display components
                    content_placeholder, status_placeholder, thinking_placeholder = stream_content_display()
                    
                    status_placeholder.info("Connecting to AI and generating content...")
                    
                    def generate_content_with_streaming():
                        """Generate content using the streaming API and manage content streaming response"""
                        # Create local variable to accumulate content
                        accumulated_content = [""]
                        
                        # Initialize accumulated_thinking for streaming display
                        if 'accumulated_thinking' not in st.session_state:
                            st.session_state.accumulated_thinking = ""
                        
                        # Make sure the API key is set in the settings dictionary
                        if 'settings' in st.session_state:
                            st.session_state.settings['anthropic_api_key'] = st.session_state.get('anthropic_api_key', '')
                        
                        # Define the inner callback function that ONLY accumulates content - NO EXTRACTION DURING STREAMING
                        def update_stream(content=None, thinking_content=None):
                            if content is not None:
                                # ONLY accumulate content during streaming, don't extract anything
                                accumulated_content[0] += content
                                st.session_state.accumulated_content = accumulated_content[0]
                                html_content = accumulated_content[0].replace('\n', '<br>')
                                html = f"""
                                <div class="content-container">
                                    {html_content}
                                </div>
                                """
                                content_placeholder.markdown(html, unsafe_allow_html=True)
                            
                            if thinking_content is not None:
                                # Just accumulate thinking content
                                st.session_state.accumulated_thinking += thinking_content
                                thinking_placeholder.markdown(f"<div class='thinking-container'>{st.session_state.accumulated_thinking}</div>", unsafe_allow_html=True)
                        
                        # Make the API call with the streaming callback
                        response = generate_content_from_headings(
                            st.session_state.requirements,
                            st.session_state.meta_and_headings,
                            st.session_state.settings,
                            stream=True,
                            stream_callback=update_stream
                        )
                        
                        # Now streaming is complete, let's extract everything from the full content
                        print(f"\nSTREAMING COMPLETED - Content length: {len(accumulated_content[0])} chars")
                        
                        # Step 1: Extract meta information and headings
                        meta_title_pattern = r"META TITLE:\s*(.*?)(?:\n|$)"
                        meta_desc_pattern = r"META DESCRIPTION:\s*(.*?)(?:\n|$)"
                        heading_pattern = r"HEADING STRUCTURE:(.*?)(?=\n\n|$)"
                        
                        meta_title_match = re.search(meta_title_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                        meta_desc_match = re.search(meta_desc_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                        heading_match = re.search(heading_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                        
                        # Save content first
                        response["content"] = accumulated_content[0]
                        
                        # Step 2: Update response dict with metadata
                        if meta_title_match:
                            meta_title = meta_title_match.group(1).strip()
                            print(f"Found meta title: {meta_title}")
                            response["meta_title"] = meta_title
                            st.session_state["meta_title_input"] = meta_title
                        else:
                            print("No meta title found in response")
                        
                        if meta_desc_match:
                            meta_desc = meta_desc_match.group(1).strip()
                            print(f"Found meta description: {meta_desc}")
                            response["meta_description"] = meta_desc
                            st.session_state["meta_desc_input"] = meta_desc
                        else:
                            print("No meta description found in response")
                        
                        if heading_match:
                            heading_text = heading_match.group(1).strip()
                            heading_lines = [line.strip() for line in heading_text.split('\n') 
                                            if line.strip() and re.match(r'^#{1,6}\s+', line.strip())]
                            print(f"EXTRACTED {len(heading_lines)} markdown headings from HEADING STRUCTURE section")
                            for h in heading_lines:
                                print(f"  - {h}")
                            response["headings"] = heading_lines
                        else:
                            # If no HEADING STRUCTURE section, try other extraction methods
                            all_extracted_headings = extract_headings_from_content(accumulated_content[0])
                            if all_extracted_headings:
                                print(f"EXTRACTED {len(all_extracted_headings)} HEADINGS VIA FALLBACK")
                                for h in all_extracted_headings:
                                    print(f"  - {h}")
                                response["headings"] = all_extracted_headings
                        
                        # Step 3: Update session state
                        if "meta_title" in response:
                            st.session_state["meta_title_input"] = response["meta_title"]
                        if "meta_description" in response:
                            st.session_state["meta_desc_input"] = response["meta_description"]
                        
                        # Update meta_and_headings dictionary
                        if "meta_and_headings" not in st.session_state:
                            st.session_state.meta_and_headings = {}
                            
                        if "meta_title" in response:
                            st.session_state.meta_and_headings["meta_title"] = response["meta_title"]
                        if "meta_description" in response:
                            st.session_state.meta_and_headings["meta_description"] = response["meta_description"]
                        if "headings" in response:
                            st.session_state.meta_and_headings["headings"] = response["headings"]
                            print(f"SAVED {len(response['headings'])} HEADINGS TO SESSION STATE")
                        
                        # Store thinking process
                        if 'accumulated_thinking' in st.session_state:
                            st.session_state.content_thinking_process = st.session_state.accumulated_thinking
                        
                        return response

                # Call the streaming version directly
                response = generate_content_with_streaming()
                
                # Process the response data
                st.session_state.generated_markdown = response.get("content", "")
                st.session_state.generated_html = markdown_to_html(st.session_state.generated_markdown)
                st.session_state.content_generation_complete = True
                
                st.session_state.content_thinking_process = response.get("thinking", "")
                
                # Save meta information to session state
                if response.get("meta_title"):
                    st.session_state["meta_title_input"] = response.get("meta_title")
                if response.get("meta_description"):
                    st.session_state["meta_desc_input"] = response.get("meta_description")
                
                # Update meta_and_headings dictionary
                if "meta_and_headings" in st.session_state:
                    if response.get("meta_title"):
                        st.session_state.meta_and_headings["meta_title"] = response.get("meta_title")
                    if response.get("meta_description"):
                        st.session_state.meta_and_headings["meta_description"] = response.get("meta_description")
                    if response.get("headings"):
                        st.session_state.meta_and_headings["headings"] = response.get("headings")
                
                # Store thinking process
                if 'accumulated_thinking' in st.session_state:
                    if 'content_thinking_process' not in st.session_state:
                        st.session_state.content_thinking_process = st.session_state.get('accumulated_thinking', '')
                    else:
                        # Append to existing thinking content
                        st.session_state.content_thinking_process += st.session_state.accumulated_thinking
                
                # Debug expander for thinking process
                with st.expander("Debug - Content Generation Thinking Process", expanded=False):
                    if 'accumulated_thinking' in st.session_state:
                        st.markdown(
                            """
                            <div class="content-container">
                            {content}
                            </div>
                            """.format(content=st.session_state.accumulated_thinking.replace('\n', '<br>')),
                            unsafe_allow_html=True
                        )
                
                status_placeholder.success("Generation complete!")
                st.rerun()  # Refresh to update UI
            except Exception as e:
                st.error(f"Error generating content: {str(e)}")
                st.error(traceback.format_exc())
                st.session_state['content_generation_failed'] = True
                
                # Combine both error handlers
                st.error(f"Additional error details: {e.__class__.__name__}")
                import traceback
                st.text_area("Error Details", traceback.format_exc(), height=300)

        # Update meta info BEFORE displaying content to ensure it's available in the Analysis tab
        print()
        st.session_state.meta_and_headings["meta_title"] = st.session_state.get("meta_title_input", "")
        st.session_state.meta_and_headings["meta_description"] = st.session_state.get("meta_desc_input", "")

    # Show the content and download options
    display_generated_content()
    
    # Add a "Regenerate Content" button
    if st.button(" Regenerate Content", help="Generate new content using the same settings and headings"):
        # Set flag to force regeneration
        st.session_state['force_regenerate'] = True
        st.rerun()
        
    zip_buffer = create_download_zip()
    st.download_button(
        label="Download All as ZIP",
        data=zip_buffer,
        file_name="seo_content_package.zip",
        mime="application/zip",
        key="download_zip_step3_final"
    )

def generate_and_display_content():
    """
    Generate the full content based on the meta and headings structure.
    """
    if "disable_api_call" in st.session_state and st.session_state.disable_api_call:
        st.warning("API calls are disabled. Using mock data.")
        st.session_state.generated_markdown = "# Example Generated Content\n\nThis is mock content."
        st.session_state.generated_html = markdown_to_html(st.session_state.generated_markdown)
        st.session_state.content_generation_complete = True
    
    # Check if heading generation is complete
    if not st.session_state.get("heading_generation_complete", False):
        st.error("Please generate headings first.")
    
    # Ensure we have meta and headings
    if "meta_and_headings" not in st.session_state or not st.session_state.meta_and_headings:
        st.error("Missing meta information and headings. Please generate headings first.")
    
    # Check if API key is available
    if (
        'settings' not in st.session_state 
        or not st.session_state.settings.get('anthropic_api_key')
    ):
        st.error("""
        Please enter your Anthropic API key in the Settings tab. 
        The system needs this to generate content.
        """)
    
    # If streaming is enabled
    if not st.session_state.get("disable_streaming", False):
        # Create placeholders for streaming content
        content_placeholder, status_placeholder, thinking_placeholder = stream_content_display()
        
        try:
            # Initialize the process
            status_placeholder.info("Connecting to AI and generating content…")

            #HERE

            def run_generation():
                """Generate content using the streaming API and manage content streaming response"""
                # Create local variable to accumulate content
                accumulated_content = [""]
                
                # Initialize accumulated_thinking in session state
                if 'accumulated_thinking' not in st.session_state:
                    st.session_state.accumulated_thinking = ""
                
                # Make sure the API key is set in the settings dictionary
                if 'settings' in st.session_state:
                    st.session_state.settings['anthropic_api_key'] = st.session_state.get('anthropic_api_key', '')
                
                # Define the inner callback function - THIS RUNS DURING STREAMING
                def update_stream(content=None, thinking_content=None):
                    if content:
                        accumulated_content[0] += content
                        st.session_state.accumulated_content = accumulated_content[0]
                        html_content = accumulated_content[0].replace('\n', '<br>')
                        html = f"""
                        <div class="content-container">
                            {html_content}
                        </div>
                        """
                        content_placeholder.markdown(html, unsafe_allow_html=True)
                        
                        # NO EXTRACTION HERE - we only display the content
                    
                    if thinking_content is not None:
                        # Just accumulate thinking content
                        st.session_state.accumulated_thinking += thinking_content
                        thinking_placeholder.markdown(f"<div class='thinking-container'>{st.session_state.accumulated_thinking}</div>", unsafe_allow_html=True)
                
                # Make the API call with the streaming callback
                response = generate_meta_and_headings(
                    st.session_state.requirements, 
                    st.session_state.settings, 
                    st.session_state.business_data,
                    stream=True, 
                    stream_callback=update_stream
                )
                
                # EVERYTHING BELOW THIS HAPPENS AFTER STREAMING IS COMPLETE
                print("\nSTREAMING COMPLETED - NOW EXTRACTING ALL METADATA")
                print(f"FULL CONTENT LENGTH: {len(accumulated_content[0])} characters")
                
                # Step 1: Extract meta title and description AFTER streaming
                meta_title_pattern = r"META TITLE:\s*(.*?)(?:\n|$)"
                meta_desc_pattern = r"META DESCRIPTION:\s*(.*?)(?:\n|$)"
                heading_pattern = r"HEADING STRUCTURE:(.*?)(?=\n\n|$)"
                
                meta_title_match = re.search(meta_title_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                meta_desc_match = re.search(meta_desc_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                heading_match = re.search(heading_pattern, accumulated_content[0], re.DOTALL | re.IGNORECASE)
                
                # Process meta title AFTER streaming
                if meta_title_match:
                    meta_title = meta_title_match.group(1).strip()
                    print(f"Found meta title: {meta_title}")
                    response["meta_title"] = meta_title
                    st.session_state["meta_title_input"] = meta_title
                else:
                    print("No meta title found in response")
                
                # Process meta description AFTER streaming
                if meta_desc_match:
                    meta_desc = meta_desc_match.group(1).strip()
                    print(f"Found meta description: {meta_desc}")
                    response["meta_description"] = meta_desc
                    st.session_state["meta_desc_input"] = meta_desc
                else:
                    print("No meta description found in response")
                
                # Process headings AFTER streaming with detailed logging
                try:
                    found_headings = []
                    
                    # Method 1: Extract from HEADING STRUCTURE section
                    if heading_match:
                        heading_text = heading_match.group(1).strip()
                        print(f"\nFound HEADING STRUCTURE section: \n{heading_text}")
                        # Extract ALL markdown headings (with any number of # characters)
                        heading_lines = [line.strip() for line in heading_text.split('\n') 
                                        if line.strip() and re.match(r'^#{1,6}\s+', line.strip())]
                        print(f"Extracted {len(heading_lines)} markdown headings from HEADING STRUCTURE section")
                        # Print each heading for debugging
                        for h in heading_lines:
                            print(f"  - {h}")
                        found_headings = heading_lines
                    
                    # Method 2: Try markdown headings if needed
                    if not found_headings:
                        print("\nNo valid HEADING STRUCTURE section found, trying markdown headings...")
                        heading_lines = re.findall(r'^(#{1,6}\s+.+?)$', accumulated_content[0], re.MULTILINE)
                        if heading_lines:
                            print(f"Found {len(heading_lines)} markdown headings")
                            found_headings = heading_lines
                    
                    # Method 3: Try H1, H2 format if needed
                    if not found_headings:
                        print("\nNo markdown headings found, trying H1, H2 format...")
                        heading_lines = re.findall(r'^(H[1-6]:\s+.+?)$', accumulated_content[0], re.MULTILINE)
                        if heading_lines:
                            print(f"Found {len(heading_lines)} Hn format headings")
                            found_headings = heading_lines
                    
                    # Store the headings AFTER streaming
                    if found_headings:
                        print(f"\nFINAL HEADING COUNT: {len(found_headings)}")
                        response["headings"] = found_headings
                        
                        # Store headings in session state
                        if "meta_and_headings" not in st.session_state:
                            st.session_state.meta_and_headings = {}
                        st.session_state.meta_and_headings["headings"] = found_headings
                        
                        # Also store meta info in session state
                        if meta_title_match:
                            st.session_state.meta_and_headings["meta_title"] = meta_title_match.group(1).strip()
                        if meta_desc_match:
                            st.session_state.meta_and_headings["meta_description"] = meta_desc_match.group(1).strip()
                        if "token_usage" in response:
                            st.session_state.meta_and_headings["token_usage"] = response["token_usage"]
                    else:
                        print("\nWARNING: NO HEADINGS FOUND! Using fallback heading.")
                        # Create a fallback heading if none were found
                        fallback_heading = f"# {st.session_state.get('primary_keyword', 'Professional Services')}"
                        response["headings"] = [fallback_heading]
                        if "meta_and_headings" not in st.session_state:
                            st.session_state.meta_and_headings = {}
                        st.session_state.meta_and_headings["headings"] = [fallback_heading]
                except Exception as e:
                    print(f"[ERROR] Exception during heading extraction: {e}")
                    import traceback
                    traceback.print_exc()
                    # Always provide a fallback so UI does not break
                    fallback_heading = f"# {st.session_state.get('primary_keyword', 'Professional Services')}"
                    response["headings"] = [fallback_heading]
                    if "meta_and_headings" not in st.session_state:
                        st.session_state.meta_and_headings = {}
                    st.session_state.meta_and_headings["headings"] = [fallback_heading]
                
                # Store the thinking process for future reference
                if 'accumulated_thinking' in st.session_state:
                    st.session_state.headings_thinking_process = st.session_state.accumulated_thinking
                
                # Save the full accumulated content to the response object
                response["content"] = accumulated_content[0]
                
                return response
            
            # Immediately call the function to execute in the correct scope (outside the function)
            response = run_generation()
            
            # Make sure we capture the FULL content into generated_markdown
            if "content" in response:
                print(f"Setting generated_markdown with full content: {len(response['content'])} chars")
                st.session_state.generated_markdown = response.get("content", "")
            else:
                print("WARNING: No 'content' field in response")
                st.session_state.generated_markdown = response.get("content", "")
            
            # Convert to HTML for display
            st.session_state.generated_html = markdown_to_html(st.session_state.generated_markdown)
            st.session_state.content_generation_complete = True
            
            st.session_state.content_thinking_process = response.get("thinking", "")
            
            # Make sure meta information is preserved for analysis tab
            if response.get("meta_title"):
                st.session_state["meta_title_input"] = response.get("meta_title")
            if response.get("meta_description"):
                st.session_state["meta_desc_input"] = response.get("meta_description")
            
            # Also update the meta_and_headings dictionary to ensure consistency
            if "meta_and_headings" in st.session_state:
                if response.get("meta_title"):
                    st.session_state.meta_and_headings["meta_title"] = response.get("meta_title")
                if response.get("meta_description"):
                    st.session_state.meta_and_headings["meta_description"] = response.get("meta_description")
                if response.get("headings"):
                    st.session_state.meta_and_headings["headings"] = response.get("headings")
            
            # Store the thinking process for review WITHOUT CLEARING previous thinking
            # This way we preserve the complete thinking history
            if 'accumulated_thinking' in st.session_state:
                if 'content_thinking_process' not in st.session_state:
                    st.session_state.content_thinking_process = st.session_state.get('accumulated_thinking', '')
                else:
                    # Append to existing thinking content instead of replacing it
                    st.session_state.content_thinking_process += st.session_state.accumulated_thinking
            
            # Create a debug expander to keep thinking process visible even after generation completes
            with st.expander("Debug - Content Generation Thinking Process", expanded=False):
                if 'accumulated_thinking' in st.session_state:
                    st.markdown(
                        """
                        <div class="content-container">
                        {content}
                        </div>
                        """.format(content=st.session_state.accumulated_thinking.replace('\n', '<br>')),
                        unsafe_allow_html=True
                    )
            
            status_placeholder.success(" Generation complete!")
            
        except Exception as e:
            status_placeholder.error(f"Error generating content: {str(e)}")
            st.error(traceback.format_exc())
            st.session_state['content_generation_failed'] = True
    else:
        # Non-streaming version
        with st.spinner("Generating content..."):
            try:
                # Make sure the API key is set in the settings dictionary
                if 'settings' in st.session_state:
                    st.session_state.settings['anthropic_api_key'] = st.session_state.get('anthropic_api_key', '')
                    
                response = generate_content_from_headings(
                    st.session_state.requirements,
                    st.session_state.meta_and_headings,
                    st.session_state.settings
                )
                
                st.session_state.generated_markdown = response.get("content", "")
                st.session_state.generated_html = markdown_to_html(st.session_state.generated_markdown)
                st.session_state.content_generation_complete = True
                
                st.session_state.token_usage_content = {
                    "input_tokens": response.get("input_tokens", 0),
                    "output_tokens": response.get("output_tokens", 0),
                    "total_tokens": response.get("total_tokens", 0)
                }
                
                # Make sure headings are properly saved for editing
                extract_and_save_headings(response)
                
                # Create a debug expander to preserve thinking process 
                if "thinking" in response:
                    with st.expander("Debug - Non-streaming Thinking Process", expanded=False):
                        st.markdown(
                            """
                            <div class="content-container">
                            {content}
                            </div>
                            """.format(content=response['thinking'].replace('\n', '<br>')),
                            unsafe_allow_html=True
                        )
            
            except Exception as e:
                st.error(f"Error generating content: {str(e)}")
                st.error(traceback.format_exc())
                st.session_state['content_generation_failed'] = True
    
    # Display the generated content
    display_generated_content()
    
    return True
