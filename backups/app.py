#Old APp.py start
import streamlit as st
import pandas as pd
import re
import warnings
from main import parse_cora_report, generate_meta_and_headings, markdown_to_html, generate_content_from_headings
import os
from collections import Counter
import io
import zipfile
import json
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl.styles.stylesheet")

# ==== DEV MODE CONFIGURATION ====
DEV_MODE = False  # Set to True to enable dev mode
# ===============================
def display_token_usage(usage_type, token_usage, sidebar=True):
    input_tokens = token_usage.get('input_tokens', 0)
    output_tokens = token_usage.get('output_tokens', 0)
    total_tokens = token_usage.get('total_tokens', 0) or (input_tokens + output_tokens)
    
    input_cost = (input_tokens / 1000000) * 3
    output_cost = (output_tokens / 1000000) * 15
    total_cost = input_cost + output_cost
    
    container = st.sidebar if sidebar else st
    container.markdown(f"### {usage_type} Token Usage")
    col1, col2, col3 = container.columns(3)
    col1.metric("Input Tokens", input_tokens, delta=f"${input_cost:.4f}", delta_color="off")
    col2.metric("Output Tokens", output_tokens, delta=f"${output_cost:.4f}", delta_color="off")
    col3.metric("Total Tokens", total_tokens, delta=f"${total_cost:.4f}", delta_color="off")
    return total_cost

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

def initialize_session_state():
    defaults = {
        'step': 1,
        'generated_markdown': '',
        'generated_html': '',
        'save_path': '',
        'meta_and_headings': {},
        'original_meta_and_headings': {},
        'original_requirements': {},
        'requirements': {},
        'basic_tunings': {},
        'configured_headings': {},
        'file': None,
        'anthropic_api_key': '',
        'auto_generate_content': False,
        'custom_entities': [],
        'content_token_usage': {},
        'heading_token_usage': {},
        'configured_settings': {},
        'images_required': 0
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# Call at the start of the app
initialize_session_state()

# Add CSS to make index column fit content
st.markdown("""
<style>
    .row_heading.level0 {width: auto !important; white-space: nowrap;}
    .blank {width: auto !important; white-space: nowrap;}
</style>
""", unsafe_allow_html=True)


# Utility function to analyze content
def analyze_content(markdown_content, requirements):
    text_content = re.sub(
        r'^#+.*$|[*_`~]|[<][^>]+[>]|https?://\S+|[\n\r.,;:!?()\[\]{}"\'-]',
        ' ',
        markdown_content.lower(),
        flags=re.MULTILINE
    )
    text_content = re.sub(r'\s+', ' ', text_content).strip()
    tokens = text_content.split()
    token_text = ' ' + ' '.join(tokens) + ' '
    word_counts = Counter(tokens)

    analysis = {
        "primary_keyword": requirements.get("primary_keyword", ""),
        "primary_keyword_count": 0,
        "word_count": len(tokens),
        "variations": {},
        "heading_structure": {"H1": 0, "H2": 0, "H3": 0, "H4": 0, "H5": 0, "H6": 0},
        "lsi_keywords": {},
        "entities": {}
    }

    # Single pass for all counts
    primary_keyword = requirements.get("primary_keyword", "").lower().strip()
    if primary_keyword:
        analysis["primary_keyword_count"] = token_text.count(f" {primary_keyword} ")

    for var in requirements.get("variations", []):
        var_lower = var.lower().strip()
        count = token_text.count(f" {var_lower} ")
        analysis["variations"][var] = {"count": count, "status": "✅" if count > 0 else "❌"}

    for kw, target in requirements.get("lsi_keywords", {}).items():
        kw_lower = kw.lower().strip()
        count = token_text.count(f" {kw_lower} ")
        target_count = target.get("count", 1) if isinstance(target, dict) else target
        analysis["lsi_keywords"][kw] = {"count": count, "target": target_count, "status": "✅" if count >= target_count else "❌"}

    for entity in requirements.get("entities", []):
        entity_lower = entity.lower().strip()
        count = token_text.count(f" {entity_lower} ")
        analysis["entities"][entity] = {"count": count, "status": "✅" if count > 0 else "❌"}

    # Heading counts
    for line in markdown_content.split("\n"):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            analysis["heading_structure"][f"H{len(match.group(1))}"] += 1

    return analysis


def render_extracted_data():
    """
    Displays a persistent expander titled 'View Complete Extracted Data'
    showing the extracted SEO requirements in tables. If configured settings
    exist (headings in Step 2 or word count in Step 3), they are appended.
    """
    def display_dataframe(title, data, key_prefix):
        """Helper function to consistently display dataframes with a title"""
        st.write(f"**{title}:**")
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, height=200, hide_index=True)
        else:
            st.write(f"**{title}:** None")
    
    requirements = st.session_state.get("requirements", {})
    primary_keyword = st.session_state.get("primary_keyword", "Not found")
    variations = st.session_state.get("variations", [])
    lsi_keywords = st.session_state.get("lsi_keywords", {})
    entities = st.session_state.get("entities", [])
    
    with st.expander("View Complete Extracted Data", expanded=True):
        st.markdown("### Extracted Requirements")
        st.write(f"**Primary Keyword:** {primary_keyword}")
        # You might want to pull word count target from basic_tunings or requirements
        st.write(f"**Word Count Target:** {st.session_state.get('basic_tunings', {}).get('Word Count', 'N/A')} words") 
        # Variations
        display_dataframe("Keyword Variations", [{"Variation": v} for v in variations], "variations")

        # LSI Keywords Display
        if isinstance(lsi_keywords, dict):
            lsi_data = [{"Keyword": k, "Frequency": v} for k, v in lsi_keywords.items()]
        else:
            lsi_data = [{"Keyword": k} for k in lsi_keywords]
        display_dataframe("LSI Keywords", lsi_data, "lsi")
        
        # Entities Display
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
                    if 'entities' in st.session_state.requirements:
                        # Prepend custom entities to the existing list
                        st.session_state.requirements['entities'] = entity_list + st.session_state.requirements.get('entities', [])
                    else:
                        st.session_state.requirements['entities'] = entity_list
                    
                    st.success(f"Added {len(entity_list)} custom entities!")
                    # Rerun to show updated entities
                    st.rerun()
        
        with col2:
            # Button to clear custom entities
            if st.button("Clear Custom Entities"):
                if 'custom_entities' in st.session_state and st.session_state.custom_entities:
                    # Remove custom entities from the requirements
                    if 'entities' in st.session_state.requirements:
                        original_entities = st.session_state.requirements.get('entities', [])
                        custom_count = len(st.session_state.custom_entities)
                        # Remove the first N items (custom entities)
                        st.session_state.requirements['entities'] = original_entities[custom_count:]
                    
                    # Clear from session state
                    st.session_state.custom_entities = []
                    st.success("Custom entities cleared!")
                    # Rerun to show updated entities
                    st.rerun()
        
        # Display current custom entities
        if st.session_state.custom_entities:
            st.markdown("**Current Custom Entities:**")
            custom_ent_df = pd.DataFrame({"Entity": st.session_state.custom_entities})
            st.dataframe(custom_ent_df, use_container_width=True, height=200, hide_index=True)
        
        if requirements:
            # First, print all keys and values for debugging
            print("\n=== DEBUGGING ROADMAP REQUIREMENTS ===")
            for k, v in requirements.items():
                print(f"Key: '{k}', Value: {v}, Type: {type(v)}")
            print("=== END DEBUGGING ===\n")
            
            # Check if "Entities in H2 Tags" is in requirements and manually handle it
            if "Entities in H2 Tags" in requirements:
                # Note: This is a temporary fix - you'll want to find the root cause later
                print(f"Found 'Entities in H2 Tags' with value: {requirements['Entities in H2 Tags']}")
                if requirements["Entities in H2 Tags"] == 1:  # If it's incorrectly set to 1
                    requirements["Entities in H2 Tags"] = 6  # Manually set to 6
                    print("Corrected 'Entities in H2 Tags' value to 6")
            
            # Filter roadmap requirements and add to display data
            excluded_keys = ["Title Length", "Description Length", "primary_keyword", "variations", 
                           "lsi_keywords", "entities", "word_count", "lsi_limit"]
            
            roadmap_data = []
            for k, v in requirements.items():
                # Skip if key starts with "Number of" or is in excluded list
                if k.startswith("Number of") or k in excluded_keys:
                    continue
                roadmap_data.append({"Requirement": k, "Value": v})
                
            # Display the filtered roadmap data
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
            st.write(f"Total Headings: {configured_headings.get('total', 'N/A')}")
        
        # Configured Settings for Word Count (Step 3)
        if "configured_settings" in st.session_state:
            configured_settings = st.session_state["configured_settings"]
            st.markdown("### Configured Settings (Content)")
            st.write(f"Word Count Target: {configured_settings.get('word_count', 'N/A')}")

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
            # Determine which step to jump to
            step_num = int(dev_step.split(".")[0])
            
            # Setup necessary sample data for the selected step
            if step_num >= 2:  # Requirements or later steps
                st.session_state.file = "dummy_file"  # Just to bypass file upload check
                # Setup sample requirements (if you still need them)
                st.session_state.requirements = {
                    "primary_keyword": "Roof Replacement Garden Grove",
                    "variations": ["roof replacement in Garden Grove", "Garden Grove roof replacement"],
                    "lsi_keywords": {"roofing": {"count": 3}, "contractor": {"count": 2}},
                    "entities": ["Garden Grove", "Orange County"],
                    "word_count": 1500,
                    "Number of H2 tags": 3,
                    "Number of H3 tags": 5,
                    "Number of H4 tags": 2,
                    "Number of H5 tags": 0,
                    "Number of H6 tags": 0,
                    "Number of heading tags": 11,
                    "Number of Images": 2
                }
                # Also, set them in separate session keys:
                st.session_state.primary_keyword = st.session_state.requirements.get("primary_keyword", "")
                st.session_state.variations = st.session_state.requirements.get("variations", [])
                st.session_state.lsi_keywords = st.session_state.requirements.get("lsi_keywords", {})
                st.session_state.entities = st.session_state.requirements.get("entities", [])

                
            if step_num >= 3:  # Meta & Headings or later steps
                # Setup sample meta & headings
                st.session_state.meta_and_headings = {
                    "meta_title": "Roof Replacement Garden Grove | Professional Roofing Services",
                    "meta_description": "Expert roof replacement services in Garden Grove. Get durable, quality roofing with our professional team. Free estimates & competitive pricing!",
                    "headings": ["H1: Professional Roof Replacement Services in Garden Grove", 
                               "H2: Why Choose Our Garden Grove Roof Replacement Services", 
                               "H2: Our Roof Replacement Process",
                               "H3: Initial Roof Inspection"]
                }
                
            if step_num >= 5:  # View Results
                # Load content from markdown file
                try:
                    file_path = "seo_content_roof_replacement_garden_grove.md"
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        st.session_state.generated_markdown = content
                        st.session_state.generated_html = markdown_to_html(content)
                        st.session_state.images_required = 2
                        # Add analysis data for future Analysis tab
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
            
            # Set the step and rerun
            st.session_state.step = step_num
            st.rerun()
    
    anthropic_api_key = st.text_input(
        "Anthropic API Key", 
        value="",
        type="password",
        help="Enter your Anthropic API key. This will not be stored permanently."
    )
    st.session_state['anthropic_api_key'] = anthropic_api_key
    
    if not anthropic_api_key:
        st.warning("Please enter your Anthropic API key to use this app.")
    
    if 'content_token_usage' in st.session_state or 'heading_token_usage' in st.session_state:
        # Display heading token usage if available
        heading_cost = 0
        if 'heading_token_usage' in st.session_state:
            heading_cost = display_token_usage("Heading Generation", st.session_state['heading_token_usage'])
            
        # Display content token usage if available
        content_cost = 0
        if 'content_token_usage' in st.session_state:
            content_cost = display_token_usage("Content Generation", st.session_state['content_token_usage'])
                
        # Display combined cost if both tokens are available
        if 'content_token_usage' in st.session_state and 'heading_token_usage' in st.session_state:
            combined_total_cost = content_cost + heading_cost
            st.sidebar.markdown("### Combined Total Cost")
            st.sidebar.metric("Total Article Cost", f"${combined_total_cost:.4f}")

# File upload section
uploaded_file = st.file_uploader("Upload CORA report", type=["xlsx", "xls"])

def process_upload():
    if 'file' not in st.session_state or not st.session_state['file']:
        st.error("Please upload a CORA report first.")
        return
    try:
        file = st.session_state['file']
        with st.spinner("Processing CORA report..."): 
            result = parse_cora_report(file)
            
            # Move debug code here AFTER result is defined
            print("\n=== DEBUGGING PARSE_CORA_REPORT RESULT ===")
            print(f"Result keys: {list(result.keys())}")
            if "requirements" in result:
                nested_reqs = result['requirements']
                print(f"Nested requirements keys: {list(nested_reqs.keys())}")
                if "Entities in H2 Tags" in nested_reqs:
                    print(f"Value for 'Entities in H2 Tags' in nested: {nested_reqs['Entities in H2 Tags']}")
            print("=== END DEBUGGING ===\n")
            
            st.session_state['primary_keyword'] = result.get("primary_keyword", "")
            st.session_state['variations'] = result.get("variations", [])
            st.session_state['lsi_keywords'] = result.get("lsi_keywords", {})
            if isinstance(result.get('lsi_keywords', {}), list):
                result['lsi_keywords'] = {kw: 1 for kw in result.get('lsi_keywords', [])}
            st.session_state['entities'] = result.get("entities", [])
            st.session_state['requirements'] = result.get("requirements", {})  # keep roadmap requirements separate if needed
            st.session_state['basic_tunings'] = result.get("basic_tunings", {})
            
            # Debug the session state AFTER it's populated
            print("\n=== DEBUGGING REQUIREMENTS SESSION STATE ===")
            if "requirements" in st.session_state:
                reqs = st.session_state['requirements']
                print(f"Requirements keys: {list(reqs.keys())}")
                if "Entities in H2 Tags" in reqs:
                    print(f"Value for 'Entities in H2 Tags': {reqs['Entities in H2 Tags']}")
            print("=== END DEBUGGING ===\n")
            st.session_state['step'] = 2
        st.success("CORA report processed successfully!")
    except Exception as e:
        st.error(f"Error processing CORA report: {str(e)}")

if uploaded_file is not None:
    st.session_state['file'] = uploaded_file
    st.success(f"Successfully uploaded: {uploaded_file.name}")
    
    if st.button("Extract Requirements"):
        process_upload()
else:
    st.info("Please upload a CORA report to get started.")

# Add this at the module level (before generate_content_flow function)
@st.cache_data
def cached_generate_content(requirements_json, headings, api_keys_json):
    """
    Cached wrapper for generate_content_from_headings to prevent redundant API calls.
    Uses JSON strings for inputs to ensure proper caching behavior.
    """
    # Convert JSON strings back to dictionaries
    requirements = json.loads(requirements_json)
    api_keys = json.loads(api_keys_json)
    return generate_content_from_headings(requirements, headings, api_keys)

def display_content_analysis():
    """Display detailed analysis of the generated content."""
    with st.spinner("Analyzing content..."):
        analysis = analyze_content(st.session_state['generated_html'], st.session_state.requirements)
        # ... (meta title/description display)
        st.write(f"**Word Count:** {analysis['word_count']}")
        images_required = st.session_state.get('images_required', st.session_state.requirements.get('Number of Images', 0))
        st.write(f"**Number of Images:** {images_required}")
        heading_counts = [f"{h.upper()} Tags: {analysis['heading_structure'][h]}" for h in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']]
        st.write(" | ".join(heading_counts))
        
        # Display LSI keyword usage
        if analysis.get('lsi_keywords'):
            display_keyword_analysis("LSI Keyword", analysis)
        
        # Display variation usage
        if analysis.get('variations'):
            display_variation_analysis(analysis)

def display_generated_content():
    """Display the generated content in tabs with preview, markdown and analysis."""
    st.success("Content generated successfully!")
    st.subheader("Generated Content")
    
    if 'generated_html' not in st.session_state or not st.session_state['generated_html']:
        try:
            import markdown
            st.session_state['generated_html'] = markdown.markdown(st.session_state['generated_markdown'])
        except Exception as e:
            st.session_state['generated_html'] = "<p>Error displaying HTML preview</p>"
            st.warning(f"Could not generate HTML preview: {str(e)}")
    
    tab1, tab2, tab3 = st.tabs(["Preview", "Markdown", "Analysis"])
    
    with tab1:
        st.markdown("""
        <style>
        .content-preview {
            font-family: 'Helvetica', 'Arial', sans-serif;
            line-height: 1.6;
            padding: 20px;
            background-color: #0b0e12;
            border-radius: 5px;
            overflow: scroll;
            box-shadow: 0px 0px 5px 2px rgb(87 87 87 / 35%);
            height: 400px;
        }
        .content-preview h1, .content-preview h2, .content-preview h3, .content-preview h4, .content-preview h5, .content-preview h6 { color: #fff; }
        .content-preview h1 { font-size: 28px; margin-top: 20px; }
        .content-preview h2 { font-size: 24px; margin-top: 18px; }
        .content-preview h3 { font-size: 20px; margin-top: 16px; }
        .content-preview p { margin-bottom: 16px; }
        </style>
        """, unsafe_allow_html=True)
        html_with_styles = f'<div class="content-preview">{st.session_state["generated_html"]}</div>'
        st.html(html_with_styles)
    
    with tab2:
        st.markdown("### Raw Markdown")
        st.text_area("Markdown Content", st.session_state['generated_markdown'], height=400, key="raw_markdown_text_area")
        st.download_button(
            label="Download Markdown",
            data=st.session_state['generated_markdown'],
            file_name=f"seo_content_{st.session_state.requirements['primary_keyword'].replace(' ', '_').lower()}.md",
            mime="text/markdown"
        )
        
        if st.session_state.get('save_path'):
            st.write(f"Content also saved to: {st.session_state['save_path']}")
    
    with tab3:
        display_content_analysis()
# Function to handle content generation flow
def generate_content_flow():
    """Generate and display content."""
    content_exists = 'generated_markdown' in st.session_state and len(st.session_state.get('generated_markdown', '')) > 0
    
    print(f"CONTENT_FLOW: Content exists in session: {content_exists}")
    if content_exists:
        print(f"CONTENT_FLOW: Content length: {len(st.session_state['generated_markdown'])}")
    
    if not content_exists:
        if st.session_state.get('auto_generate_content', False):
            print("CONTENT_FLOW: Auto-generate flag is set, initiating API call")
            st.session_state.pop('auto_generate_content', None)
            try:
                with st.status("Generating content...") as status:
                    status.update(label="🧠 Claude is thinking about your content...", state="running")
                    
                    # Keep requirements and basic_tunings as separate dictionaries
                    requirements_dict = dict(st.session_state.requirements)
                    basic_tunings_dict = dict(st.session_state.basic_tunings)

                    # Get meta title and description
                    meta_title = st.session_state.meta_and_headings.get("meta_title", "")
                    meta_description = st.session_state.meta_and_headings.get("meta_description", "")

                    # Log information for debugging
                    print(f"CONTENT_FLOW: Word count: {basic_tunings_dict.get('Word Count', 'Not set')}")
                    print(f"CONTENT_FLOW: LSI limit: {requirements_dict.get('lsi_limit', 'Not set')}")
                    print(f"CONTENT_FLOW: Meta title: {meta_title}")
                    print(f"CONTENT_FLOW: Meta description: {meta_description}")

                    # Create the combined structure for the API
                    api_payload = {
                        "requirements": requirements_dict,
                        "basic_tunings": basic_tunings_dict,
                        "meta_title": meta_title,
                        "meta_description": meta_description
                    }
                    
                    # Ensure cached_generate_content uses stable, serializable inputs
                    result = cached_generate_content(
                        json.dumps(api_payload),  # Already JSON-serialized
                        st.session_state.meta_and_headings.get("heading_structure", ""),
                        json.dumps({"anthropic_api_key": st.session_state.get('anthropic_api_key', '')})
                    )
                    
                    markdown_content = result.get('markdown', '')
                    html_content = result.get('html', '')
                    save_path = result.get('filename', '')
                    # Try to get token usage from the API result; if empty, fallback to previously stored value
                    token_usage = result.get('token_usage', {}) or st.session_state.get('content_token_usage', {})
                    if token_usage:
                        st.session_state['content_token_usage'] = token_usage
                        
                        # Display token usage using the centralized function
                        content_cost = display_token_usage("Content Generation", token_usage)
                        
                        # Also display heading cost if available
                        heading_cost = 0
                        if 'heading_token_usage' in st.session_state:
                            heading_cost = display_token_usage("Heading Generation", st.session_state['heading_token_usage'])
                        
                        # Display combined cost
                        combined_total_cost = content_cost + heading_cost
                        st.sidebar.markdown("### Combined Total Cost")
                        st.sidebar.metric("Total Article Cost", f"${combined_total_cost:.4f}")
                    print(f"CONTENT_FLOW: Content generated successfully, length: {len(markdown_content)}")
                    
                    st.session_state['generated_markdown'] = markdown_content
                    
                    if html_content:
                        st.session_state['generated_html'] = html_content
                    else:
                        try:
                            import markdown
                            st.session_state['generated_html'] = markdown.markdown(markdown_content)
                        except Exception as e:
                            st.session_state['generated_html'] = "<p>Error displaying HTML preview</p>"
                            status.update(label=f"⚠️ Content generated, but HTML preview may have errors: {str(e)}", state="complete")
                    
                    st.session_state['save_path'] = save_path
                    
                    status.update(label="✅ Content generated successfully!", state="complete")
                print("CONTENT_FLOW: Content saved to session state, forcing rerun")
                st.rerun()
            except Exception as e:
                st.error(f"Error generating content: {str(e)}")
                import traceback
                st.text_area("Error Details", traceback.format_exc(), height=300)
        else:
            if 'generate_full_content_button' not in st.session_state or not st.session_state['generate_full_content_button']:
                st.info("Click 'Generate Full Content' in the previous step to generate the content.")
                if st.button("Back to Edit Meta and Headings"):
                    st.session_state['step'] = 2.5
                    st.rerun()
    
    if content_exists:
        st.success("Content generated successfully!")
        st.subheader("Generated Content")
        
        if 'generated_html' not in st.session_state or not st.session_state['generated_html']:
            try:
                import markdown
                st.session_state['generated_html'] = markdown.markdown(st.session_state['generated_markdown'])
            except Exception as e:
                st.session_state['generated_html'] = "<p>Error displaying HTML preview</p>"
                st.warning(f"Could not generate HTML preview: {str(e)}")
        
        tab1, tab2, tab3 = st.tabs(["Preview", "Markdown", "Analysis"])
        
        with tab1:
            st.markdown("""
            <style>
            .content-preview {
                font-family: 'Helvetica', 'Arial', sans-serif;
                line-height: 1.6;
                padding: 20px;
                background-color: #0b0e12;
                border-radius: 5px;
                overflow: scroll;
                box-shadow: 0px 0px 5px 2px rgb(87 87 87 / 35%);
                height: 400px;
            }
            .content-preview h1, .content-preview h2, .content-preview h3, .content-preview h4, .content-preview h5, .content-preview h6 { color: #fff; }
            .content-preview h1 { font-size: 28px; margin-top: 20px; }
            .content-preview h2 { font-size: 24px; margin-top: 18px; }
            .content-preview h3 { font-size: 20px; margin-top: 16px; }
            .content-preview p { margin-bottom: 16px; }
            </style>
            """, unsafe_allow_html=True)
            html_with_styles = f'<div class="content-preview">{st.session_state["generated_html"]}</div>'
            st.html(html_with_styles)
        
        with tab2:
            st.markdown("### Raw Markdown")
            st.text_area("Markdown Content", st.session_state['generated_markdown'], height=400, key="raw_markdown_text_area")
            st.download_button(
                label="Download Markdown",
                data=st.session_state['generated_markdown'],
                file_name=f"seo_content_{st.session_state.requirements['primary_keyword'].replace(' ', '_').lower()}.md",
                mime="text/markdown"
            )
            
            if st.session_state.get('save_path'):
                st.write(f"Content also saved to: {st.session_state['save_path']}")
        
        with tab3:
            display_content_analysis()
        @st.cache_data
        def cached_generate_content(requirements, headings, api_keys):
            return generate_content_from_headings(requirements, headings, api_keys)

        # In generate_content_flow:
        result = cached_generate_content(updated_requirements, st.session_state.meta_and_headings.get("heading_structure", ""), {"anthropic_api_key": st.session_state.get('anthropic_api_key', '')})
                
        if st.button("Regenerate Content"):
            del st.session_state['generated_markdown']
            del st.session_state['generated_html']
            st.session_state['auto_generate_content'] = True
            st.rerun()
        
        if st.button("Start Over"):
            for key in ['generated_markdown', 'generated_html', 'save_path', 'meta_and_headings']:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state['step'] = 2
            st.rerun()
        
        if content_exists:
            display_generated_content()
        
if st.session_state.get("step", 1) == 2.5:
    requirements = st.session_state.requirements
    meta_and_headings = st.session_state.meta_and_headings
    
    if 'token_usage' in meta_and_headings:
        token_usage = meta_and_headings['token_usage']
        input_cost = (token_usage['input_tokens'] / 1000000) * 3
        output_cost = (token_usage['output_tokens'] / 1000000) * 15
        total_cost = input_cost + output_cost
        
        st.sidebar.markdown("### Token Usage")
        col1, col2, col3 = st.sidebar.columns(3)
        col1.metric("Input Tokens", token_usage['input_tokens'], delta=f"${input_cost:.4f}", delta_color="off")
        col2.metric("Output Tokens", token_usage['output_tokens'], delta=f"${output_cost:.4f}", delta_color="off")
        col3.metric("Total Tokens", token_usage['total_tokens'], delta=f"${total_cost:.4f}", delta_color="off")
    
    st.subheader("Generated Meta Information and Heading Structure")
    
    if 'original_meta_and_headings' not in st.session_state and 'meta_and_headings' in st.session_state:
        st.session_state['original_meta_and_headings'] = st.session_state['meta_and_headings'].copy()
    
    if 'original_requirements' not in st.session_state and 'requirements' in st.session_state:
        st.session_state['original_requirements'] = st.session_state['requirements'].copy()
    
    meta_title_input = st.text_input(
        "Meta Title", 
        value=meta_and_headings.get("meta_title", ""), 
        help="Edit the generated meta title if needed.",
        key="meta_title_input"
    )
    
    ideal_title_length = requirements.get('requirements', {}).get('CP480', 60)
    min_title_length = max(int(ideal_title_length * 0.95), 40)
    
    meta_title_chars = len(meta_title_input)
    st.caption(f"Character count: {meta_title_chars}/{ideal_title_length} " + 
              (f"✅" if min_title_length <= meta_title_chars <= ideal_title_length else f"⚠️ Ideal length is {min_title_length}-{ideal_title_length} characters"))
    
    meta_description_input = st.text_area(
        "Meta Description", 
        value=meta_and_headings.get("meta_description", ""), 
        height=100, 
        help="Edit the generated meta description if needed.",
        key="meta_description_input"
    )
    
    ideal_desc_length = requirements.get('requirements', {}).get('CP380', 160)
    min_desc_length = max(int(ideal_desc_length * 0.95), 120)
    
    meta_desc_chars = len(meta_description_input)
    st.caption(f"Character count: {meta_desc_chars}/{ideal_desc_length} " + 
              (f"✅" if min_desc_length <= meta_desc_chars <= ideal_desc_length else f"⚠️ Ideal length is {min_desc_length}-{ideal_desc_length} characters"))
    
    word_count = requirements.get('word_count', 1500)
    word_count_input = st.number_input(
        "Word Count Target", 
        min_value=500,
        max_value=10000,
        value=word_count,
        step=100,
        help="Edit the target word count for content generation.",
        key="word_count_input"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        lsi_limit = requirements.get('lsi_limit', 100)
        lsi_limit_input = st.number_input(
            "Number of LSI Keywords to Include", 
            min_value=10,
            max_value=500,
            value=lsi_limit,
            step=10,
            help="Limit the number of LSI keywords used in content generation.",
            key="lsi_limit_input"
        )
    
    with col2:
        lsi_keywords = requirements.get('lsi_keywords', {})
        if isinstance(lsi_keywords, dict):
            total_lsi = len(lsi_keywords)
        elif isinstance(lsi_keywords, list):
            total_lsi = len(lsi_keywords)
        else:
            total_lsi = 0
            
        st.write(f"Available LSI Keywords: {total_lsi}")
        st.caption(f"Using top {min(lsi_limit_input, total_lsi)} LSI keywords")
    
    heading_structure_input = st.text_area(
        "Heading Structure", 
        value=meta_and_headings.get("heading_structure", ""), 
        height=400, 
        help="Edit the generated heading structure if needed.",
        key="heading_structure_input"
    )
    
    # Calculate and display the heading count comparison
    if heading_structure_input:
        # Get the most up-to-date heading requirements (either from CORA or user modifications)
        required_headings = {
            "h1": 1,  # Always expect 1 H1 tag
        }
        
        # Check if user has configured custom heading counts
        if 'configured_headings' in st.session_state:
            required_headings.update({
                "h2": st.session_state.configured_headings.get('h2', 0),
                "h3": st.session_state.configured_headings.get('h3', 0),
                "h4": st.session_state.configured_headings.get('h4', 0),
                "h5": st.session_state.configured_headings.get('h5', 0),
                "h6": st.session_state.configured_headings.get('h6', 0)
            })
        else:
            # Fall back to original CORA requirements if no user modifications
            required_headings.update({
                "h2": requirements.get('requirements', {}).get('Number of H2 tags', 0),
                "h3": requirements.get('requirements', {}).get('Number of H3 tags', 0),
                "h4": requirements.get('requirements', {}).get('Number of H4 tags', 0),
                "h5": requirements.get('requirements', {}).get('Number of H5 tags', 0),
                "h6": requirements.get('requirements', {}).get('Number of H6 tags', 0)
            })
        
        # Count actual headings in the markdown
        actual_headings = {"h1": 0, "h2": 0, "h3": 0, "h4": 0, "h5": 0, "h6": 0}
        
        for line in heading_structure_input.split('\n'):
            if line.strip().startswith('#'):
                # Count consecutive # symbols at the start of the line
                heading_level = 0
                for char in line.strip():
                    if char == '#':
                        heading_level += 1
                    else:
                        break
                
                if 1 <= heading_level <= 6:
                    actual_headings[f"h{heading_level}"] += 1
        
        # Display the heading count comparison
        st.write("### Heading Count Comparison")
        
        col1, col2, col3 = st.columns(3)
        col1.markdown("**Heading Level**")
        col2.markdown("**Required Count**")
        col3.markdown("**Actual Count**")
        
        total_required = sum(required_headings.values())
        total_actual = sum(actual_headings.values())
        
        for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            req_count = required_headings[level]
            act_count = actual_headings[level]
            col1.markdown(f"**{level.upper()}**")
            col2.markdown(f"{req_count}")
            col3.markdown(f"{act_count}")
        
        # Display the total
        col1.markdown("**TOTAL**")
        col2.markdown(f"**{total_required}**")
        col3.markdown(f"**{total_actual}**")
    
    def generate_full_content_button():
        print("===== GENERATE FULL CONTENT BUTTON CLICKED =====")
        if 'generated_markdown' in st.session_state:
            print("Clearing existing generated_markdown from session state")
            del st.session_state['generated_markdown']
        if 'generated_html' in st.session_state:
            print("Clearing existing generated_html from session state")
            del st.session_state['generated_html']

        # Save the edited meta title, meta description, and heading structure to session state
        print("Updating meta title from user input")
        st.session_state.meta_and_headings['meta_title'] = st.session_state.meta_title_input
        
        print("Updating meta description from user input")
        st.session_state.meta_and_headings['meta_description'] = st.session_state.meta_description_input
        
        print("Updating heading structure from user input")
        st.session_state.meta_and_headings['heading_structure'] = st.session_state.heading_structure_input

        if 'requirements' in st.session_state:
            # Get the word count from the input field, which should be initialized from CORA
            word_count = st.session_state.get('word_count_input', st.session_state.requirements.get('word_count', 1500))
            lsi_limit = st.session_state.get('lsi_limit_input', 20)
            
            print(f"Updating word_count to {word_count} and lsi_limit to {lsi_limit}")
            st.session_state.requirements['word_count'] = word_count
            st.session_state.requirements['lsi_limit'] = lsi_limit
        
        print("SETTING auto_generate_content to True to force API call")
        st.session_state['auto_generate_content'] = True
        print("Setting step to 3 for content generation")
        st.session_state['step'] = 3
        st.rerun()
    
    col1, col2 = st.columns(2)
    with col1:
        generate_button = st.button("Generate Full Content", use_container_width=True, on_click=generate_full_content_button)

    with col2:
        if st.button("Back to Requirements"):
            st.session_state['step'] = 2
            st.rerun()

if st.session_state.get("step", 1) == 2:
    requirements = st.session_state.requirements
    meta_and_headings = st.session_state.meta_and_headings
    
    render_extracted_data()
    primary_keyword = st.session_state.get("primary_keyword", "Not found")
    variations = st.session_state.get("variations", [])
    lsi_keywords = st.session_state.get("lsi_keywords", {})
    entities = st.session_state.get("entities", [])

    st.subheader("Configure Headings")
    st.markdown("Adjust the number of headings if needed. These values will be used in the prompt.")
    default_h1 = st.session_state.get('basic_tunings', {}).get('Number of H1 tags', 1)
    default_h2 = st.session_state.get('basic_tunings', {}).get('Number of H2 tags', 4)
    default_h3 = st.session_state.get('basic_tunings', {}).get('Number of H3 tags', 8)
    default_h4 = st.session_state.get('basic_tunings', {}).get('Number of H4 tags', 0)
    default_h5 = st.session_state.get('basic_tunings', {}).get('Number of H5 tags', 0)
    default_h6 = st.session_state.get('basic_tunings', {}).get('Number of H6 tags', 0)
    
    heading_sum = default_h1 + default_h2 + default_h3 + default_h4 + default_h5 + default_h6
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        h1_count = st.number_input("H1 Headings", min_value=0, max_value=100, value=default_h1, key='h1_config')
    with col2:
        h2_count = st.number_input("H2 Headings", min_value=0, max_value=100, value=default_h2, key='h2_config')
    with col3:
        h3_count = st.number_input("H3 Headings", min_value=0, max_value=100, value=default_h3, key='h3_config')
    with col4:
        h4_count = st.number_input("H4 Headings", min_value=0, max_value=100, value=default_h4, key='h4_config')
    with col5:
        h5_count = st.number_input("H5 Headings", min_value=0, max_value=100, value=default_h5, key='h5_config')
    with col6:
        h6_count = st.number_input("H6 Headings", min_value=0, max_value=100, value=default_h6, key='h6_config')
    
    total_headings = h1_count + h2_count + h3_count + h4_count + h5_count + h6_count
    with col6:
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
    
    def show_prompt_modal(prompt_title, prompt_content):
        with st.expander(f"🔍 {prompt_title}", expanded=True):
            st.code(prompt_content)
    
    col1, col2 = st.columns(2)
    with col1:
        generate_button = st.button("Generate Meta Title, Description and Headings", use_container_width=True)

    if generate_button:
        if not st.session_state.get('anthropic_api_key', ''):
            st.error("Please enter your Anthropic API key in the sidebar.")
        else:
            with st.spinner("🔄 Generating meta information and heading structure..."):
                try:
                    settings = {
                        'model': 'claude',
                        'anthropic_api_key': st.session_state.get('anthropic_api_key', ''),
                    }
                    
                    status = st.status("Generating meta and headings...", expanded=True)
                    status.write("📤 Sending request to Claude API...")
                    
                    api_key = st.session_state.get('anthropic_api_key', '')
                    
                    if not api_key:
                        st.error("Please provide an API key in the sidebar.")
                        status.update(label="Error", state="error")
                    else:
                        if 'configured_headings' in st.session_state:
                            requirements = st.session_state.requirements.copy()
                            
                            if 'requirements' not in requirements:
                                requirements['requirements'] = {}
                            
                            requirements['requirements']['Number of H2 tags'] = st.session_state.configured_headings['h2']
                            requirements['requirements']['Number of H3 tags'] = st.session_state.configured_headings['h3']
                            requirements['requirements']['Number of H4 tags'] = st.session_state.configured_headings['h4']
                            requirements['requirements']['Number of H5 tags'] = st.session_state.configured_headings['h5']
                            requirements['requirements']['Number of H6 tags'] = st.session_state.configured_headings['h6']
                            requirements['requirements']['Number of heading tags'] = st.session_state.configured_headings['total']
                        else:
                            requirements = st.session_state.requirements

                        total_headings = (
                            requirements.get('requirements', {}).get('Number of H2 tags', 4) +
                            requirements.get('requirements', {}).get('Number of H3 tags', 8) +
                            requirements.get('requirements', {}).get('Number of H4 tags', 0) +
                            requirements.get('requirements', {}).get('Number of H5 tags', 0) +
                            requirements.get('requirements', {}).get('Number of H6 tags', 0)
                        )
                        status.write(f"🧠 Claude is thinking about {total_headings + 1} headings for \"{requirements.get('primary_keyword', '')}\"...")
                        
                        meta_and_headings = generate_meta_and_headings(requirements, settings)
                        status.write("✅ Response received! Processing results...")
                        
                        # Save token usage information to session state
                        if 'token_usage' in meta_and_headings:
                            st.session_state['heading_token_usage'] = meta_and_headings['token_usage']
                            display_token_usage("Heading Generation", meta_and_headings['token_usage'])
                        
                        st.session_state['meta_and_headings'] = meta_and_headings
                        st.session_state['original_meta_and_headings'] = dict(meta_and_headings)
                        st.session_state['original_requirements'] = dict(requirements)
                        st.session_state['step'] = 2.5  # Move to heading editing step
                        status.update(label="✅ Meta and headings generated successfully!", state="complete")
                        st.rerun()
                except Exception as e:
                    error_msg = f"Error generating meta and headings: {str(e)}"
                    st.error(error_msg)
                    st.error("⚠️ Please check the error above before proceeding.")
                    import traceback
                    st.text_area("Error Details", traceback.format_exc(), height=300)
                    st.warning("To retry, please click the 'Generate Meta Title...' button again.")
    
    if st.button("Back to Requirements"):
        st.session_state['step'] = 2
        st.rerun()

if st.session_state.get("step", 1) == 3:
    print("==== ENTERING STEP 3 CONTENT GENERATION FLOW ====")
    print(f"Session State Keys: {list(st.session_state.keys())}")
    print(f"Has 'generated_markdown' in session: {'generated_markdown' in st.session_state}")
    
    if st.session_state.get('auto_generate_content', False):
        print("Auto generate content is TRUE - clearing any existing content")
        if 'generated_markdown' in st.session_state:
            print("FORCING REMOVAL of generated_markdown in step 3 initialization")
            del st.session_state['generated_markdown']
        if 'generated_html' in st.session_state:
            print("FORCING REMOVAL of generated_html in step 3 initialization")
            del st.session_state['generated_html']

    st.session_state.configured_settings = {"word_count": st.session_state.get("word_count_input", st.session_state.requirements.get("word_count", 1500))}
    
    render_extracted_data()
    
    st.subheader("Step 3: Generate Content")
    generate_content_flow()

def create_download_zip():
    md_content = st.session_state.get("generated_markdown", "")
    html_content = st.session_state.get("generated_html", "")
    requirements = st.session_state.get("requirements", {})
    analysis = analyze_content(html_content, requirements)
    
    extracted_data = f"Primary Keyword: {requirements.get('primary_keyword', 'Not found')}\n"
    extracted_data += f"Word Count Target: {requirements.get('word_count', 'N/A')} words\n"
    
    variations = requirements.get("variations", [])
    extracted_data += "Keyword Variations: " + (", ".join(variations) if variations else "None") + "\n"
    
    lsi_keywords = requirements.get("lsi_keywords", {})
    if isinstance(lsi_keywords, dict):
        lsi_str = "\n".join([f"{k}: {v}" for k, v in lsi_keywords.items()])
    else:
        lsi_str = ", ".join(lsi_keywords)
    extracted_data += "LSI Keywords:\n" + (lsi_str if lsi_str else "None") + "\n"
    
    entities = requirements.get("entities", [])
    extracted_data += "Entities: " + (", ".join(entities) if entities else "None") + "\n"
    
    roadmap_reqs = requirements.get("requirements", {})
    filtered_reqs = {k: v for k, v in roadmap_reqs.items() 
                     if not k.startswith("Number of H") and k != "Number of heading tags" and k not in ["CP480", "CP380"]
    }
    if filtered_reqs:
        roadmap_str = "\n".join([f"{k}: {v}" for k, v in filtered_reqs.items()])
    else:
        roadmap_str = "None"
    extracted_data += "Roadmap Requirements:\n" + roadmap_str + "\n"
    
    if "configured_headings" in st.session_state:
        cfg = st.session_state["configured_headings"]
        cfg_str = (
            f"H2 Headings: {cfg.get('h2', 'N/A')}\n"
            f"H3 Headings: {cfg.get('h3', 'N/A')}\n"
            f"H4 Headings: {cfg.get('h4', 'N/A')}\n"
            f"H5 Headings: {cfg.get('h5', 'N/A')}\n"
            f"H6 Headings: {cfg.get('h6', 'N/A')}\n"
            f"Total Headings (includes H1): {cfg.get('total', 'N/A')}\n"
        )
        extracted_data += "Configured Settings (Headings):\n" + cfg_str + "\n"
    if "configured_settings" in st.session_state:
        cs = st.session_state["configured_settings"]
        extracted_data += f"Configured Settings (Content):\nWord Count Target: {cs.get('word_count', 'N/A')}\n"
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("content.html", html_content)
        zip_file.writestr("content.md", md_content)
        zip_file.writestr("analysis.json", json.dumps(analysis, indent=4))
        zip_file.writestr("extracted_data.txt", extracted_data)
    zip_buffer.seek(0)
    return zip_buffer

zip_buffer = create_download_zip()
st.download_button(
    label="Download All as ZIP",
    data=zip_buffer,
    file_name="seo_content_package.zip",
    mime="application/zip"
)
#Old APp.py End