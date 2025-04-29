import streamlit as st
import pandas as pd
import io
import zipfile
import json
from services.analysis_service import analyze_content
from models import SEORequirements
from utils.logger import get_logger

# logger setup
logger = get_logger(__name__)

def display_token_usage(usage_type, token_usage, sidebar=True):
    """
    Display token usage metrics in the Streamlit UI.
    
    Args:
        usage_type (str): Type of token usage to display (e.g., 'Heading Generation')
        token_usage (dict): Token usage information with input_tokens, output_tokens, etc.
        sidebar (bool): Whether to display in sidebar or main area
    
    Returns:
        float: Total cost of the operation
    """
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

def render_extracted_data():
    """
    Displays a persistent expander titled 'View Complete Extracted Data'
    showing the extracted SEO requirements in tables. If configured settings
    exist (headings in Step 2 or word count in Step 3), they are appended.
    """
    # Only show if requirements exist
    if 'requirements' not in st.session_state or not st.session_state.requirements:
        return
    
    req_dict = st.session_state.requirements
    
    with st.expander("View Complete Extracted Data", expanded=False):
        def display_dataframe(title, data, key_prefix):
            """Helper function to consistently display dataframes with a title"""
            if data:
                st.markdown(f"#### {title}")
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True, key=f"{key_prefix}_df")
                
        # Primary keyword and variations
        primary_keyword = req_dict.get('primary_keyword', 'Not found')
        st.markdown(f"#### Primary Keyword: `{primary_keyword}`")
        
        variations = req_dict.get('variations', [])
        if variations:
            variation_data = [{"Variation": v} for v in variations]
            display_dataframe("Keyword Variations", variation_data, "var")
        
        # LSI Keywords
        lsi_keywords = req_dict.get('lsi_keywords', {})
        if lsi_keywords:
            if isinstance(lsi_keywords, dict):
                lsi_data = [{"Keyword": k, "Required Count": v if isinstance(v, int) else v.get('count', 1) if isinstance(v, dict) else 1} 
                           for k, v in lsi_keywords.items()]
            else:
                lsi_data = [{"Keyword": k, "Required Count": 1} for k in lsi_keywords]
            
            display_dataframe("LSI Keywords", lsi_data, "lsi")
        
        # Entities
        entities = req_dict.get('entities', [])
        if entities:
            entity_data = [{"Entity": e} for e in entities]
            display_dataframe("Entities", entity_data, "entity")
        
        # Word count
        word_count = req_dict.get('word_count', 0)
        st.markdown(f"#### Word Count Target: `{word_count}` words")
        
        # Display heading requirements from original requirements
        if 'requirements' in req_dict:
            reqs = req_dict['requirements']
            h1 = reqs.get('CP380', 1)
            h2 = reqs.get('Number of H2 tags', 4)
            h3 = reqs.get('Number of H3 tags', 8)
            h4 = reqs.get('Number of H4 tags', 0)
            h5 = reqs.get('Number of H5 tags', 0)
            h6 = reqs.get('Number of H6 tags', 0)
            total = reqs.get('Number of heading tags', h1 + h2 + h3 + h4 + h5 + h6)
            
            heading_data = [
                {"Heading Type": "H1", "Count": h1},
                {"Heading Type": "H2", "Count": h2},
                {"Heading Type": "H3", "Count": h3},
                {"Heading Type": "H4", "Count": h4},
                {"Heading Type": "H5", "Count": h5},
                {"Heading Type": "H6", "Count": h6},
                {"Heading Type": "Total", "Count": total},
            ]
            display_dataframe("Original Heading Requirements", heading_data, "orig_heading")
        
        # Show configured heading settings if available
        if 'configured_headings' in st.session_state:
            cfg = st.session_state['configured_headings']
            heading_data = [
                {"Heading Type": "H1", "Count": cfg.get('h1', 1)},
                {"Heading Type": "H2", "Count": cfg.get('h2', 4)},
                {"Heading Type": "H3", "Count": cfg.get('h3', 8)},
                {"Heading Type": "H4", "Count": cfg.get('h4', 0)},
                {"Heading Type": "H5", "Count": cfg.get('h5', 0)},
                {"Heading Type": "H6", "Count": cfg.get('h6', 0)},
                {"Heading Type": "Total", "Count": cfg.get('total', 13)},
            ]
            display_dataframe("Configured Heading Settings", heading_data, "cfg_heading")
        
        # Show configured word count if available
        if 'configured_settings' in st.session_state:
            settings = st.session_state['configured_settings']
            if 'word_count' in settings:
                st.markdown(f"#### Configured Word Count: `{settings['word_count']}` words")
        
        # Other roadmap requirements
        if 'requirements' in req_dict:
            reqs = req_dict['requirements']
            filtered_reqs = {k: v for k, v in reqs.items() 
                         if not k.startswith("Number of H") and k != "Number of heading tags" and k not in ["CP480", "CP380"]}
            
            if filtered_reqs:
                other_data = [{"Requirement": k, "Value": v} for k, v in filtered_reqs.items()]
                display_dataframe("Other Requirements", other_data, "other")

def display_content_analysis():
    """
    Display detailed analysis of the generated content.
    """
    if 'generated_markdown' not in st.session_state or not st.session_state.generated_markdown:
        st.warning("No content has been generated yet.")
        return
    
    markdown_content = st.session_state.generated_markdown
    requirements = st.session_state.requirements
    
    analysis = analyze_content(markdown_content, requirements)
    
    st.subheader("Content Analysis")
    
    # Add some CSS for better styling of the dropdowns
    st.markdown("""
    <style>
        .stExpander {
            border: 1px solid #ddd;
            border-radius: 8px;
            margin-bottom: 10px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .density-badge {
            background-color: #f0f2f6;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 0.8em;
            margin-left: 6px;
        }
        
        .analysis-metric {
            margin-bottom: 12px;
            padding: 8px;
            border-radius: 5px;
            background-color: #f8f9fa;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Display Meta Title and Description
    with st.expander("Meta Title & Description", expanded=True):
        # Check for meta information in a more robust way
        meta_title = ""
        meta_description = ""
        
        # Check all possible sources for meta information in priority order
        if 'meta_title_input' in st.session_state and st.session_state.get('meta_title_input'):
            meta_title = st.session_state.get('meta_title_input')
        elif 'meta_and_headings' in st.session_state and st.session_state.meta_and_headings.get('meta_title'):
            meta_title = st.session_state.meta_and_headings.get('meta_title')
        else:
            meta_title = analysis.get('meta_title', '')
        
        if 'meta_desc_input' in st.session_state and st.session_state.get('meta_desc_input'):
            meta_description = st.session_state.get('meta_desc_input')
        elif 'meta_and_headings' in st.session_state and st.session_state.meta_and_headings.get('meta_description'):
            meta_description = st.session_state.meta_and_headings.get('meta_description')
        else:
            meta_description = analysis.get('meta_description', '')
        
        # Use fallbacks if still empty
        if not meta_title:
            meta_title = "Not available"
        if not meta_description:
            meta_description = "Not available"
        
        meta_title_length = len(meta_title)
        meta_description_length = len(meta_description)
        
        # Display meta info with more visibility
        st.markdown("##### Meta Title")
        st.code(meta_title, language=None)
        st.markdown(f"Length: **{meta_title_length}** characters")
        
        st.markdown("##### Meta Description")
        st.code(meta_description, language=None)
        st.markdown(f"Length: **{meta_description_length}** characters")
        
        # Add a visual indicator for optimal lengths
        title_optimal = 50 <= meta_title_length <= 60
        desc_optimal = 150 <= meta_description_length <= 160
        
        if not title_optimal:
            st.warning(f"Meta title length ({meta_title_length}) is {'too short' if meta_title_length < 50 else 'too long'} for optimal SEO. Aim for 50-60 characters.")
        else:
            st.success("Meta title length is optimal for SEO.")
            
        if not desc_optimal:
            st.warning(f"Meta description length ({meta_description_length}) is {'too short' if meta_description_length < 150 else 'too long'} for optimal SEO. Aim for 150-160 characters.")
        else:
            st.success("Meta description length is optimal for SEO.")
    
    # Overall score
    st.markdown(f"#### Overall Score: {analysis['score']}%")
    
    # Progress bar for overall score
    st.progress(analysis['score'] / 100)
    
    # Basic metrics in a clean layout
    col1, col2 = st.columns(2)
    
    # Word count in first column
    with col1:
        word_count = analysis['word_count']
        target_word_count = analysis['word_count_target']
        word_count_met = analysis['word_count_met']
        
        word_count_color = "green" if word_count_met else "red"
        st.markdown(f"##### Word Count: <span style='color:{word_count_color}'>{word_count}/{target_word_count}</span>", unsafe_allow_html=True)
    
    # Primary keyword usage and image count in second column
    with col2:
        primary_keyword = analysis['primary_keyword']
        primary_keyword_count = analysis['primary_keyword_count']
        primary_keyword_density = analysis.get('primary_keyword_density', 0)
        primary_keyword_color = "green" if primary_keyword_count > 0 else "red"
        
        # Primary keyword with density
        st.markdown(
            f"##### Primary Keyword: <span style='color:{primary_keyword_color}'>{primary_keyword} "
            f"({primary_keyword_count} occurrences, {primary_keyword_density:.2f}% density)</span>", 
            unsafe_allow_html=True
        )
        
        # Image count
        image_count = analysis.get('image_count', 0)
        required_images = analysis.get('required_images', 0)
        images_met = analysis.get('images_met', False)
        image_color = "green" if images_met else "red"
        
        st.markdown(
            f"##### Image Count: <span style='color:{image_color}'>{image_count}/{required_images}</span>", 
            unsafe_allow_html=True
        )
    
    st.markdown("---")
    
    # Heading structure in expander
    with st.expander("Heading Structure", expanded=False):
        heading_req = analysis['heading_requirements']
        heading_actual = analysis['heading_structure']
        
        heading_data = []
        for level in ["H1", "H2", "H3", "H4", "H5", "H6"]:
            req = heading_req.get(level, 0)
            actual = heading_actual.get(level, 0)
            met = actual >= req
            
            heading_data.append({
                "Heading Type": level,
                "Required": req,
                "Actual": actual,
                "Status": "✅" if met else "❌"
            })
        
        df_heading = pd.DataFrame(heading_data)
        st.dataframe(df_heading, use_container_width=True, key="heading_analysis_df")
        
        # Show a single summary message for headings if any are missing
        missing_headings = df_heading[df_heading['Status'] == "❌"]
        if not missing_headings.empty:
            st.warning(f"**{len(missing_headings)} heading types don't meet requirements.** Please check the table above.")
    
    # Variations in expander
    if analysis['variations']:
        with st.expander("Keyword Variations", expanded=False):
            # Add a summary of total variations
            total_variation_count = analysis.get('total_variation_count', 0)
            total_variation_density = analysis.get('total_variation_density', 0)
            
            st.markdown(f"**Total Variations**: {total_variation_count} occurrences ({total_variation_density:.2f}% density)")
            st.markdown("---")
            
            variation_data = []
            for var, info in analysis['variations'].items():
                if isinstance(info, dict):
                    count = info.get('count', 0)
                    density = info.get('density', 0)
                    met = info.get('met', count > 0)
                else:
                    # Handle old format where info is just the count
                    count = info
                    met = count > 0
                    density = 0
                
                variation_data.append({
                    "Variation": var,
                    "Occurrences": count,
                    "Density (%)": f"{density:.2f}%" if density else "N/A",
                    "Status": "✅" if met else "❌"
                })
            
            df_var = pd.DataFrame(variation_data)
            st.dataframe(df_var, use_container_width=True, key="var_analysis_df")
            
            # Show a single summary for variations
            missing_variations = [row for row in variation_data if row["Status"] == "❌"]
            if missing_variations:
                st.warning(f"**{len(missing_variations)} keyword variations are missing.** Please check the table above.")
    
    # LSI Keywords in expander
    if analysis['lsi_keywords']:
        with st.expander("LSI Keywords", expanded=False):
            # Add a summary of total LSI keywords
            total_lsi_count = analysis.get('total_lsi_count', 0)
            total_lsi_density = analysis.get('total_lsi_density', 0)
            
            st.markdown(f"**Total LSI Keywords**: {total_lsi_count} occurrences ({total_lsi_density:.2f}% density)")
            st.markdown("---")
            
            lsi_data = []
            for keyword, info in analysis['lsi_keywords'].items():
                count = info['count']
                target = info['target']
                met = info['met']
                density = info.get('density', 0)
                
                lsi_data.append({
                    "Keyword": keyword,
                    "Required": target,
                    "Actual": count,
                    "Density (%)": f"{density:.2f}%" if density else "N/A",
                    "Status": "✅" if met else "❌"
                })
            
            df_lsi = pd.DataFrame(lsi_data)
            st.dataframe(df_lsi, use_container_width=True, key="lsi_analysis_df")
            
            # Show a single summary for LSI keywords
            missing_lsi = [row for row in lsi_data if row["Status"] == "❌"]
            if missing_lsi:
                st.warning(f"**{len(missing_lsi)} LSI keywords don't meet frequency requirements.** Please check the table above.")
    
    # Entities in expander
    if analysis['entities']:
        with st.expander("Entities", expanded=False):
            # Add a summary of total entities
            total_entity_count = analysis.get('total_entity_count', 0)
            total_entity_density = analysis.get('total_entity_density', 0)
            
            st.markdown(f"**Total Entities**: {total_entity_count} occurrences ({total_entity_density:.2f}% density)")
            st.markdown("---")
            
            entity_data = []
            for entity, info in analysis['entities'].items():
                if isinstance(info, dict):
                    count = info.get('count', 0)
                    met = info.get('met', count > 0)
                    density = info.get('density', 0)
                else:
                    # Handle old format where info is just the count
                    count = info
                    met = count > 0
                    density = 0
                
                entity_data.append({
                    "Entity": entity,
                    "Occurrences": count,
                    "Density (%)": f"{density:.2f}%" if density else "N/A",
                    "Status": "✅" if met else "❌"
                })
            
            df_entity = pd.DataFrame(entity_data)
            st.dataframe(df_entity, use_container_width=True, key="entity_analysis_df")
            
            # Show a single summary for entities
            missing_entities = [row for row in entity_data if row["Status"] == "❌"]
            if missing_entities:
                st.warning(f"**{len(missing_entities)} entities aren't mentioned at all.** Please check the table above.")

def display_generated_content():
    """
    Display the generated content in tabs with preview, markdown and analysis.
    """
    if 'generated_markdown' not in st.session_state or not st.session_state.generated_markdown:
        st.warning("No content has been generated yet.")
        return
    
    markdown_content = st.session_state.generated_markdown
    html_content = st.session_state.generated_html
    
    # Create tabs for preview, markdown, analysis
    tabs = st.tabs(["Preview", "Markdown", "Analysis"])
    
    # Preview tab
    with tabs[0]:
        st.markdown("""
            <style>
                iframe {
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 5px;
                    background-color: white;
                }
            </style>
        """, unsafe_allow_html=True)
        
        st.components.v1.html(html_content, height=600, scrolling=True)
        
        if 'images_required' in st.session_state and st.session_state.images_required > 0:
            st.info(f"Note: This content requires {st.session_state.images_required} images that you should add manually.")
    
    # Markdown tab
    with tabs[1]:
        st.markdown("### Markdown Source")
        st.text_area("Markdown Content", markdown_content, height=400)
        
        # Download buttons
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="Download as Markdown",
                data=markdown_content,
                file_name=f"seo_content_{st.session_state.requirements.get('primary_keyword', 'content').replace(' ', '_').lower()}.md",
                mime="text/markdown",
                key="download_markdown_ui_content"
            )
        
        with col2:
            st.download_button(
                label="Download as HTML",
                data=html_content,
                file_name=f"seo_content_{st.session_state.requirements.get('primary_keyword', 'content').replace(' ', '_').lower()}.html",
                mime="text/html",
                key="download_html_ui_content"
            )
    
    # Analysis tab
    with tabs[2]:
        display_content_analysis()

def stream_content_display():
    """
    Create a placeholder for streaming content and return it.
    This allows real-time updates of content as it's being generated,
    and now properly displays Claude's internal thinking process.
    
    Returns:
        tuple: (content_placeholder, status_placeholder, thinking_placeholder) - Streamlit placeholders for updating
    """
    st.subheader("Content Generation in Progress...")
    status_placeholder = st.empty()
    status_placeholder.info("Starting content generation...")
    
    st.markdown("""
    <style>
    .thinking-container {
        border: 1px solid #d1e6fa;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 10px;
        background-color: rgb(14 17 23);
        max-height: 600px;
        overflow-y: auto;
        color: #fff;
        font-size: 14px;
        line-height: 1.5;
        white-space: pre-wrap;
        font-family: monospace;
    }
    .content-container {
        border: 1px solid #d1e6fa;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 10px;
        background-color: rgb(14 17 23);
        max-height: 600px;
        overflow-y: auto;
        color: #fff;
        font-size: 14px;
        line-height: 1.5;
        white-space: pre-wrap;
    }
    .thinking-header {
        color: #7764E4;
        margin-bottom: 10px;
        font-weight: bold;
        font-size: 16px;
    }
    .content-header {
        color: #0068C9;
        margin-bottom: 10px;
        font-weight: bold;
        font-size: 16px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state for tracking accumulated thinking and content
    if 'accumulated_thinking' not in st.session_state:
        st.session_state.accumulated_thinking = ""
    if 'accumulated_content' not in st.session_state:
        st.session_state.accumulated_content = ""
    
    # Reset accumulated content (but NOT accumulated thinking)
    st.session_state.accumulated_content = ""
    
    # Create two dedicated columns - one for thinking and one for content
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<p class='thinking-header'>Claude's Thinking Process</p>", unsafe_allow_html=True)
        thinking_container = st.container()
        thinking_placeholder = thinking_container.empty()
        thinking_placeholder.markdown("<div class='thinking-container'>Waiting for Claude's thinking process...</div>", unsafe_allow_html=True)
    
    with col2:
        st.markdown("<p class='content-header'>Generated Content</p>", unsafe_allow_html=True)
        content_container = st.container()
        content_placeholder = content_container.empty()
        content_placeholder.markdown("<div class='content-container'>Content will appear here as it's generated...</div>", unsafe_allow_html=True)
    
    return content_placeholder, status_placeholder, thinking_placeholder

def create_download_zip():
    """
    Create a ZIP file containing all generated content and analysis
    
    Returns:
        io.BytesIO: Buffer containing the ZIP file
    """
    md_content = st.session_state.get("generated_markdown", "")
    html_content = st.session_state.get("generated_html", "")
    requirements = st.session_state.get("requirements", {})
    analysis = analyze_content(md_content, requirements)
    
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
                     if not k.startswith("Number of H") and k != "Number of heading tags" and k not in ["CP480", "CP380"]}
    
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

def show_prompt_modal(prompt_title, prompt_content):
    """
    Display a modal dialog with prompt information.
    
    Args:
        prompt_title (str): Title of the prompt modal
        prompt_content (str): Content to display in the modal
    """
    st.markdown(f"<details><summary>{prompt_title}</summary><pre>{prompt_content}</pre></details>", unsafe_allow_html=True)

def initialize_session_state():
    """
    Initialize Streamlit session state with default values.
    """
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
        'images_required': 0,
        'settings': {
            'model': 'claude',
            'anthropic_api_key': '',
            'generate_tables': False,
            'generate_lists': False,
            'generate_images': False,
        }
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
