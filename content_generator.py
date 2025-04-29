import anthropic
from models import SEORequirements
from utils.logger import get_logger
from utils.errors import GenerationError, ValidationError, expect
import re
 
# logger setup
logger = get_logger(__name__)

# Constants for model selection
CLAUDE_MODEL = "claude-3-7-sonnet-latest"

def call_claude_api(system_prompt, user_prompt, api_key, is_content_generation=False, stream=False, stream_callback=None):
    expect(bool(api_key), "API key is required", ValidationError)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        model = CLAUDE_MODEL
        
        # Default token and budget settings (can be parameterised later via settings)
        max_tokens = 50000 if is_content_generation else 2000
        thinking_budget = 49999 if is_content_generation else 1999

        # Detailed debug information instead of stdout prints
        logger.debug(
            (
                f"Calling Claude API | mode={'content_generation' if is_content_generation else 'heading_generation'} | "
                f"max_tokens={max_tokens} | thinking_budget={thinking_budget} | "
                f"prompt_len={len(user_prompt)} | key_prefix={api_key[:5]}*** | stream={stream}"
            )
        )
        if len(user_prompt) < 50:
            logger.warning("User prompt seems too short; response quality may suffer.")

        # If streaming is requested, return a streaming response object
        if stream:
            try:
                # Enable extended thinking for streaming responses
                stream_response = client.messages.stream(
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    model=model,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": thinking_budget
                    }
                )
                
                complete_content = ""
                full_thinking = ""
                
                # Handle the callback if provided
                if stream_callback and callable(stream_callback):
                    # Create a function to process the streamed response
                    def process_streamed_response(stream_obj):
                        nonlocal complete_content
                        nonlocal full_thinking
                        
                        # Use the context manager pattern with 'with' statement
                        with stream_obj as stream:
                            for event in stream:
                                if event.type == "content_block_delta":
                                    if event.delta.type == "thinking_delta":
                                        # Capture thinking process
                                        thinking_delta = event.delta.thinking
                                        full_thinking += thinking_delta
                                        # Update the thinking display
                                        stream_callback(thinking_content=thinking_delta, content="")
                                    elif event.delta.type == "text_delta":
                                        # Capture content
                                        content_delta = event.delta.text
                                        complete_content += content_delta
                                        # Update the content display
                                        stream_callback(content=content_delta, thinking_content="")
                                elif event.type == "message_delta" and event.delta.stop_reason:
                                    # Log the stop reason for debugging
                                    logger.debug(f"Stream stopped: {event.delta.stop_reason}")
                        
                        # Return collected content and thinking
                        return {
                            "content": complete_content,
                            "thinking": full_thinking
                        }
                    
                    # Process the streamed response
                    result = process_streamed_response(stream_response)
                    return result
                else:
                    # If no callback is provided, still process the stream but don't update UI
                    with stream_response as stream:
                        for event in stream:
                            if event.type == "content_block_delta":
                                if event.delta.type == "thinking_delta":
                                    full_thinking += event.delta.thinking
                                elif event.delta.type == "text_delta":
                                    complete_content += event.delta.text
                    
                    return {
                        "content": complete_content,
                        "thinking": full_thinking
                    }
                    
            except Exception as e:
                logger.error(f"Error in streaming response: {str(e)}")
                raise GenerationError(f"Failed to stream Claude API response: {str(e)}")
        else:
            # For non-streaming requests, still enable extended thinking mode
            try:
                response = client.messages.create(
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    model=model,
                    thinking={
                        "type": "enabled",
                        "budget_tokens": thinking_budget
                    }
                )
                
                # Extract thinking content and regular text content
                thinking_content = ""
                text_content = ""
                
                for block in response.content:
                    if block.type == "thinking":
                        thinking_content += block.thinking
                    elif block.type == "text":
                        text_content += block.text
                
                logger.debug(f"Claude API response received | content_len={len(text_content)} | thinking_len={len(thinking_content)}")
                
                return {
                    "content": text_content,
                    "thinking": thinking_content
                }
            except Exception as e:
                logger.error(f"Error calling Claude API: {str(e)}")
                raise GenerationError(f"Failed to call Claude API: {str(e)}")

    except Exception as e:
        logger.error(f"Error in Claude API call preparation: {str(e)}")
        raise GenerationError(f"Failed to prepare Claude API call: {str(e)}")

def generate_meta_and_headings(requirements, settings=None, business_data='', stream=False, stream_callback=None):
    if settings is None:
        settings = {}
    
    model = settings.get('model', 'claude')
    anthropic_api_key = settings.get('anthropic_api_key', '')
    
    if model == 'claude':
        expect(bool(anthropic_api_key), "Claude API key must be provided to use Claude", ValidationError)
    
    primary_keyword = requirements.get('primary_keyword', '')
    variations = requirements.get('variations', [])
    lsi_dict = requirements.get('lsi_keywords', {})
    entities = requirements.get('entities', [])
    word_count = requirements.get('Word Count', 1500)
    
    # Get heading requirements from the requirements dictionary
    heading_structure = {
        "h1": requirements.get('Number of H1 tags', 0),
        "h2": requirements.get('Number of H2 tags', 0),
        "h3": requirements.get('Number of H3 tags', 0),
        "h4": requirements.get('Number of H4 tags', 0),
        "h5": requirements.get('Number of H5 tags', 0),
        "h6": requirements.get('Number of H6 tags', 0),
        "total": requirements.get('Number of heading tags', 0)
    }
    
    # Get meta title and description length requirements if available
    # Use standard SEO recommended lengths as defaults
    meta_title_length = requirements.get("roadmap_requirements", {}).get("Title Length", 60)
    meta_desc_length = requirements.get("roadmap_requirements", {}).get("Description Length", 160)

    # Convert word counts to token limits (1 token ≈ ¾ words, or 4 tokens ≈ 3 words)
    title_token_limit = int(meta_title_length * (4/3))
    desc_token_limit = int(meta_desc_length * (4/3))
    word_token_limit = int(word_count * (4/3))

    # Get LSI limit from requirements (default 100)
    lsi_limit = requirements.get('lsi_limit', 100)
    
    # Get top N LSI keywords based on user preference
    lsi_formatted = ""
    if isinstance(lsi_dict, dict) and lsi_dict:
        top_lsi_keywords = sorted(lsi_dict.items(), key=lambda x: x[1], reverse=True)[:min(10, len(lsi_dict))]
        lsi_formatted = "\n".join([f"- '{kw}' => at least {freq} occurrences" for kw, freq in top_lsi_keywords])
    elif isinstance(lsi_dict, list) and lsi_dict:
        # Convert list to dict with frequency 1
        lsi_dict_converted = {kw: 1 for kw in lsi_dict}
        top_lsi_keywords = list(lsi_dict_converted.items())[:min(10, len(lsi_dict))]
        lsi_formatted = "\n".join([f"- '{kw}' => at least {freq} occurrences" for kw, freq in top_lsi_keywords])
    else:
        lsi_formatted = "- No LSI keywords available\n"
    
    # Prepare the system and user prompts
    system_prompt = """
You are a professional SEO content strategist and copywriter. Your job is to create optimized content strategies that rank well in search engines. Your task is to generate a user friendly heading outline utilizing the headings as specified and required by the user.
You have a strong understanding of SEO best practices, entity based SEO and semantic SEO. You write content that ranks well in search engine results. You are also an expert in content writing and can write content that is engaging and informative. You understand the needs of the client and their desired and strict requirements. You will not deviate from the requirements. You are capable of following the requirements strictly. You are creative and capable of delivering content that stays topically and semantically relevent to the specific page. You use specific token limits for titles and descriptions.
"""
   # Inject roadmap fields as a string
    additional_requirements = ""
    for key, val in requirements['roadmap_requirements'].items():
        if key not in [
            'primary_keyword', 'variations', 'lsi_keywords', 'entities',
            'word_count', 'Number of H1 tags', 'Number of H2 tags',
            'Number of H3 tags', 'Number of H4 tags', 'Number of H5 tags',
            'Number of H6 tags', 'Number of heading tags', 'lsi_limit',
            'meta_title', 'meta_description'
        ] and not isinstance(val, (dict, list)):
            additional_requirements += f"- {key}: {val}\n"
    
    user_prompt_heading = f"""
Please create a meta title, meta description, and heading structure for a piece of content about \"{primary_keyword}\".

<requirements>
- Important business info and details to take into account. This is important information, follow it strictly and do not deviate from it. <business info> {business_data if business_data else 'None provided'}<business info>

- Primary Keyword: {primary_keyword}
- Variations to consider: {', '.join(variations)}
- LSI Keywords to Include:{lsi_formatted}
- Entities to Include: {', '.join(entities)}

- <Important Requirements> NOTE the ":" is a separator between requirement and count needed | This is the requirement: This will be how many is needed 
{additional_requirements}
</Important Requirements>
</requirements>

<step 1>
Using the information and requirements provided tackle the SEO-optimized content. First, establish the key elements required:
- Title Tag:
- Meta Description:
- Headings Tags:
Please follow these guidelines for content structure:
1. Title: Include at least one instance of the main keyword and Exclusively use {title_token_limit} tokens to generate the title, which should be around {meta_title_length} words.
2. Meta Description: Exclusively use {desc_token_limit} tokens to generate the meta description, which should be around {meta_desc_length} words.
3. Avoid Redundancy
3A. Definition: Prevent the repetition of identical factual information, phrasing, or ideas across different sections unless necessary for context or emphasis.
3B. Guidelines:
3B1. Each section should introduce new information or a fresh perspective.
3B2. Avoid reusing the same sentences or key points under different headings.
3B3. If overlap occurs, merge sections or reframe the content to add distinct value.
3C. Example:
3C1. Redundant: Two sections both state, '[Topic] is beneficial.'
3C2. Fixed: One section defines '[Topic]', while another explains another aspect of '[Topic]'.
4. Include an FAQ if the topic involves common user questions or multiple subtopics. FAQ Section should be an H2. The Questions must each be an H3.
5. Merge variations into single headings when possible (as long as it makes sense for readability, SEO and adheres with the heading requirements).
6. IMPORTANT: Ensure and Confirm each step in the Step 1 list is met.
</step 1>

<step 2>
1. Create a heading structure with the following requirements. No Less. Do your best to fit all the requirements within the heading counts provided below. You can fit multiple entities or requirements in a single heading without stuffing it, each heading should be user-friendly. 
   - H1: {heading_structure.get("h1", 0)} headings - Do not create additional H1s unless absolutely necessary - IMPORTANT
   - H2: {heading_structure.get("h2", 0)} headings - Do not create additional H2s unless absolutely necessary - IMPORTANT
   - H3: {heading_structure.get("h3", 0)} headings - Do not create additional H3s unless absolutely necessary - IMPORTANT
   - H4: {heading_structure.get("h4", 0)} headings - Do not create additional H4s unless absolutely necessary - IMPORTANT
   - H5: {heading_structure.get("h5", 0)} headings - Do not create additional H5s unless absolutely necessary - IMPORTANT
   - H6: {heading_structure.get("h6", 0)} headings - Do not create additional H6s unless absolutely necessary - IMPORTANT

2. The headings should:
   - Contain the primary keyword and/or variations where appropriate
   - Include some LSI keywords where relevant
   - Form a logical content flow
   - Be engaging and click-worthy while still being informative
   - Be formatted in Markdown (# for H1, ## for H2, etc.)
2. Confirm all the requirements are being met in the headings.
3. Confirm all the requirements are being met in the title.
4. Confirm all the requirements are being met in the description.
5.IMPORTANT: Ensure and Confirm each step in the Step 2 list is met.
</step 2>

Format your response exactly like this:
META TITLE: [Your meta title here]
META DESCRIPTION: [Your meta description here]
HEADING STRUCTURE:
[You must always return a Complete markdown user journey friendly heading structure with # for H1, ## for H2, etc. Provided in order of the exact page layout eg.
# Heading 1
## Heading 2
### Heading 3
### Heading 3
## Heading 2
etc.]"""
    
    # Save the prompt to a file for reference
    with open("heading_prompt.txt", "w", encoding="utf-8") as f:
        f.write(user_prompt_heading)
    
    # If streaming is enabled, return the streaming response directly
    if stream:
        return call_claude_api(
            system_prompt, 
            user_prompt_heading, 
            anthropic_api_key,
            stream=True,
            stream_callback=stream_callback
        )
    
    # Call API to get meta and headings
    response = call_claude_api(system_prompt, user_prompt_heading, anthropic_api_key)
    
    # Parse the result to extract meta title, description, and headings
    meta_title = ""
    meta_description = ""
    heading_structure = ""
    heading_lines = []
    
    if "META TITLE:" in response['content']:
        meta_title = response['content'].split("META TITLE:")[1].split("META DESCRIPTION:")[0].strip()
    
    if "META DESCRIPTION:" in response['content']:
        meta_description = response['content'].split("META DESCRIPTION:")[1].split("HEADING STRUCTURE:")[0].strip()
    
    if "HEADING STRUCTURE:" in response['content']:
        heading_structure = response['content'].split("HEADING STRUCTURE:")[1].strip()
        
        # Keep the raw heading structure exactly as returned from the API
        # Just split by lines and remove any completely blank lines
        heading_lines = [line for line in heading_structure.split('\n') if line.strip()]
        
        # Only do minimal filtering to ensure we have actual headings
        # This preserves the exact order and structure
        filtered_heading_lines = []
        for line in heading_lines:
            # Keep only lines that look like headings (starting with # or H1:, etc.)
            if line.strip().startswith('#') or re.match(r'^H[1-6]:', line.strip()):
                filtered_heading_lines.append(line.strip())
        
        # If we found valid headings, use those, otherwise fall back to the raw lines
        if filtered_heading_lines:
            heading_lines = filtered_heading_lines
    
    return {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "heading_structure": heading_structure,
        "headings": heading_lines,
        "token_usage": response.get('usage', {})
    }

def generate_content_from_headings(requirements: SEORequirements | dict, meta_and_headings, settings, business_data='', stream=False, stream_callback=None):
    heading_lines = meta_and_headings.get("headings", [])
    if isinstance(heading_lines, list):
        heading_structure = "\n".join(heading_lines)
    else:
        heading_structure = meta_and_headings.get('heading_structure', '')
    expect(bool(heading_structure and heading_structure.strip()), "No valid heading structure provided", ValidationError)


    """Generate content based on the provided heading structure."""
    if settings is None:
        settings = {}
    generate_images = settings.get('generate_images', False)
    generate_lists = settings.get('generate_lists', False)
    generate_tables = settings.get('generate_tables', False)
    
    # Initialize variables
    basic_tunings_dict = {}
    requirements_dict = {}
    primary_keyword = ""
    variations = []
    lsi_keywords = []
    entities = []
    meta_title = ""
    meta_description = ""
    
    # Handle the requirements structure
    if isinstance(requirements, SEORequirements):
        primary_keyword = requirements.primary_keyword
        variations = requirements.variations
        lsi_keywords = requirements.lsi_keywords
        entities = requirements.entities
        word_count = requirements.word_count
        requirements_dict = requirements.roadmap_requirements
        basic_tunings_dict = {}
    elif isinstance(requirements, dict):
        # Direct access to top-level values if available
        primary_keyword = requirements.get('primary_keyword', '')
        variations = requirements.get('variations', [])
        lsi_keywords = requirements.get('lsi_keywords', {})
        entities = requirements.get('entities', [])
        meta_title = requirements.get('meta_title', '')
        meta_description = requirements.get('meta_description', '')
        # Override with values from meta_and_headings if present
        meta_title = meta_and_headings.get('meta_title', meta_title)
        meta_description = meta_and_headings.get('meta_description', meta_description)
        
        # Extract nested dictionaries
        if "basic_tunings" in requirements:
            # New format with separated dictionaries
            basic_tunings_dict = requirements.get("basic_tunings", {})
            requirements_dict = requirements.get("requirements", {})
        else:
            # Old format with everything in one dictionary
            requirements_dict = requirements
            basic_tunings_dict = requirements  # Fallback
    
    # Debug information via logger instead of stdout
    logger.debug(
        "Content generation input | primary_keyword=%s | variations=%d | lsi_keywords=%d | entities=%d",
        primary_keyword,
        len(variations),
        len(lsi_keywords) if isinstance(lsi_keywords, dict) else (len(lsi_keywords) if isinstance(lsi_keywords, list) else 0),
        len(entities),
    )
    
    # Get word count from the appropriate source
    word_count = 1500  # Default
    # First check the top-level requirements for word_count (which is updated in step 2.5)
    if "word_count" in requirements:
        word_count = requirements.get('word_count', 1500)
    # Fall back to the "Word Count" in basic_tunings if word_count is not found
    elif "Word Count" in basic_tunings_dict:
        word_count = basic_tunings_dict.get('Word Count', 1500)
    
    # Convert word counts to token limits (1 token ≈ ¾ words, or 4 tokens ≈ 3 words)
    word_token_limit = int(word_count * (4/3))

    # Format keyword variations
    variations_text = ", ".join(variations[:10]) if variations else "None"
    
    # Get LSI limit from requirements (default 100)
    lsi_limit = requirements.get('lsi_limit', 100)
    
    # Get top N LSI keywords based on user preference
    lsi_formatted_100 = ""
    if isinstance(lsi_keywords, dict) and lsi_keywords:
        # Sort by frequency and take top N based on lsi_limit
        top_lsi_keywords = sorted(lsi_keywords.items(), key=lambda x: x[1], reverse=True)[:min(lsi_limit, len(lsi_keywords))]
        lsi_formatted_100 = "\n".join([f"- '{kw}' => use at least {freq} times" for kw, freq in top_lsi_keywords])
    elif isinstance(lsi_keywords, list) and lsi_keywords:
        # For list format, assume frequency of 1 for each keyword
        lsi_keywords_subset = lsi_keywords[:min(lsi_limit, len(lsi_keywords))]
        lsi_formatted_100 = "\n".join([f"- '{kw}' => use at least 1 time" for kw in lsi_keywords_subset])
    
    if not lsi_formatted_100:
        lsi_formatted_100 = "- No LSI keywords available\n"
    
    # Format entities
    if entities:
        entities_text = ", ".join(entities) if entities else "None"

    else:
        entities_text = "- No specific entities required"
    
    # Get meta information if available
    meta_title = requirements.get('meta_title', '')
    meta_description = requirements.get('meta_description', '')
    
    # If meta information is not in requirements, check if it's in meta_and_headings
    if not meta_title and 'meta_and_headings' in requirements:
        meta_title = requirements.get('meta_and_headings', {}).get('meta_title', '')
        meta_description = requirements.get('meta_and_headings', {}).get('meta_description', '')
    
    # Ensure heading structure is sanitized
    if not heading_structure or not heading_structure.strip():
        heading_structure = "# " + primary_keyword
    
    # Construct the system prompt
    system_prompt = """You are an expert SEO content writer with deep knowledge about creating high-quality, engaging, and optimized content. You have a strong understanding of SEO best practices, entity based SEO and semantic SEO. You write content that ranks well in search engine results. You are also an expert in content writing and can write content that is engaging and informative. You understand the needs of the client and their desired token limit for word count requirements. If you are given a token limit, you will not use more than the token limit for that word count, you may use additional token lmits for thinking, but not the output word count. You will not deviate from the requirements. You will not add or remove any content from the headings structure. You are capable of following the requirements strictly. You are capable of detecting when content is locally based and will generate content to help in Local Search Rankings by seemlessly making accurate local references."""
    
    # Prepare enhancement instructions for the prompt
    enhancement_text = ""
    
    if generate_images:
        enhancement_text += "- Important: You MUST Provide images Under each H2 optimized for that specific section with optimized filename. Format: ![optimized image alt](optimized-name.jpg). Put space below the image, so content flows well after the image.\n"
    
    if generate_lists:
        enhancement_text += """- Important: You MUST Include bullet lists and numbered lists where appropriate to enhance content organization and readability. 
Markdown Table Return Rules: 
1. Each column header must be enclosed in | characters. Format: | Header1 | Header2 | Header3 |
2. The second row must use only - for each column (minimum 3 per column), aligned like headers
Format: |---|---|---|
For alignment (optional):
Left: |:---|
Center: |:---:|
Right: |---:|.
3. Every row must match the number of columns in the header
4. Avoid line breaks, commas in numbers, and excessive spaces inside cells
Example: Use 50+ years not 50,000 years
5. Use plain text only inside cells
No HTML, no line breaks, no bullet points
6. No hyphens for ranges — use en dash (–) or "to"
Example: 20–30 years or 20 to 30 years
7. Keep each row on one line
Do not wrap text. Shorten or simplify long content
8. Never include explanatory text inside the table
Add context before or after the table, not within it
9. Avoid escape characters unless absolutely required
10. Put space below the table, so content flows well after the table.
"""
    
    if generate_tables:
        enhancement_text += """- Important: You MUST Create comparison tables where useful to present information in a structured format
Markdown List Return Rules:

1. Use either * or - consistently for bullet points. Do not mix them.
2. Place one bullet item per line. No line wrapping or multiple lines per item.
3. For nested lists, indent using 2 spaces per level.
Example:
* Parent  
  * Child  
4. Do not include blank lines between list items unless separating sections.
5. Avoid ending punctuation unless each item is a full sentence.
6. Do not use HTML, emojis, or special formatting characters.
7. Keep language concise and uniform across all list items.
8. Avoid using numbered lists unless specifically instructed, default to bullets.
9. No headings or extra text inside the list. Explanations should go before or after the list.
10. Put space below the list, so content flows well after the list.
"""

    # Get formatted LSI keywords for the prompt
    formatted_lsi = ""
    lsi_keywords = requirements.get('lsi_keywords', {})
    if lsi_keywords:
        if isinstance(lsi_keywords, dict):
            for keyword, data in lsi_keywords.items():
                count = 1
                if isinstance(data, int):
                    count = data
                elif isinstance(data, dict) and 'count' in data:
                    count = data['count']
                formatted_lsi += f"- {keyword}: use {count} times\n"
        else:
            for keyword in lsi_keywords:
                formatted_lsi += f"- {keyword}: use at least once\n"
    
    # Construct the user prompt for content generation
    user_prompt = f"""
# SEO Content Writing Task
- Business Info to include (if applicable):<business info> {business_data if business_data else 'None provided'}<business info>
Please write a comprehensive, SEO-optimized article about **{primary_keyword}** with these Constraints:
Content Writing Guidelines:
- 1. Draft the initial content: Use {word_token_limit} tokens to generate the Content, which should be around {word_count} words.
- 1A. Perform word count using: text.split(/\s+/).filter(Boolean).length
- 1B. If word count is less than {word_token_limit}, return the content with the word count adjusted to meet the requirement of {word_count} words.
- 1C. Verify final count and confirm Draft and Word Count.
- 2. H4, H5, H6 do not need a lot of content. H3s need minimal content, but enough to get the point across.
- 3. Write in a clear, authoritative style suitable for an expert audience
- 3. Make the content deeply informative and comprehensive
- 4. Always write in active voice and maintain a conversational but professional tone
- 5. Include only factually accurate information
- 6. Ensure the content flows naturally between sections
- 7. Include the primary keyword in the first 100 words of the content
- 8. Variations, LSI keywords, and entities are used at least once when possible.
- 9. Format the content using markdown
- 10. DO NOT include any introductory notes, explanations, or meta-commentary about your process
- 11. DO NOT use placeholder text or suggest that the client should add information
- 12. DO NOT use the phrases "in conclusion" or "in summary" for the final section
- 13. Use {word_token_limit} tokens to generate the Content, which should be around {word_count} words.
- 14. Whole words only (no hyphens/subwords)
- 15. There should never be big blocks of text. We do not want big content blocks. everything should be concise and to the point, reducing fluff.
- 16. Paragraphs should not be more than 3 sentences unless absolutely necessary
- 17. Do not use any EM Dashes "—" in the content.
{enhancement_text}

Now Start Content Generation:

1. Meta Information (do not change or add to it):
- Meta Title: {meta_title}
- Meta Description: {meta_description}
    
2. Key Requirements:
- Word Count: {word_token_limit} tokens (minimum). This word count is extremely strict. Must be no less than {word_token_limit} but no more than {word_token_limit + 100}. 
- Your word count should only include raw text. Do not count Markdown syntax or provided images alt/filename (if applicable) in the word count.
- Primary Keyword: {primary_keyword}
- Use the EXACT following heading structure to generate content (**very important**: do not change or add to the headings):
<headings_structure>
{heading_structure}
</headings_structure>
    
3. Keyword Usage Requirements:
- Use the primary keyword ({primary_keyword}) in the first 100 words, in at least one H2 heading, and naturally throughout the content.

4. Keyword Variations:
- Include these keyword variations naturally: **note**: use at least 1 time each is your primary goal in this sub-step
{variations_text}
    
5. LSI Keywords to Include (with minimum frequencies): **note**: use at least 1 time each is your primary goal in this sub-step
{lsi_formatted_100}
    
6. Entities/Topics to Cover: **Note**: Your primary goal in this sub-step is to use each entity at least once within the content with a secondary goal of 8-10% entity density**
{entities_text}

IMPORTANT: Return ONLY the pure markdown content without any explanations, introductions, or notes about your approach."""

    # Save the prompt to a file for reference
    with open("content_prompt.txt", "w", encoding="utf-8") as f:
        f.write(user_prompt)
    
    # If streaming is enabled, return the streaming response directly
    if stream:
        return call_claude_api(
            system_prompt, 
            user_prompt, 
            settings.get('anthropic_api_key'), 
            is_content_generation=True,
            stream=True,
            stream_callback=stream_callback
        )
    
    # Call the API based on the settings
    if settings.get('model', '').lower() == 'claude' and settings.get('anthropic_api_key'):
        api_response = call_claude_api(system_prompt, user_prompt, settings.get('anthropic_api_key'), is_content_generation=True)
        result = api_response.get("content", "")
        token_usage = {
            "input_tokens": api_response.get("input_tokens", 0),
            "output_tokens": api_response.get("output_tokens", 0),
            "total_tokens": api_response.get("total_tokens", 0)
        }

    else:
        # Default to Claude if no valid settings are provided
        if settings.get('anthropic_api_key'):
            result, token_usage = call_claude_api(system_prompt, user_prompt, settings.get('anthropic_api_key'), is_content_generation=True)
        else:
            raise ValueError("No valid API key provided. Please provide an Anthropic API key.")
    
    # Debug: Print the raw response from the API
    print("\n=== DEBUG: RAW API RESPONSE ===")
    # The result from call_claude_api should be a dictionary with 'content' key
    if isinstance(result, dict) and 'content' in result:
        raw_content = result['content']
        print(raw_content)
    else:
        print("Unexpected result format:", result)
    print("=== END RAW API RESPONSE ===\n")
    
    # Process the result to get clean markdown
    markdown_content = extract_markdown_content(result)

    # Add this debugging/error handling
    print(f"Raw content from API (first 100 chars): {result[:100] if result else 'Empty'}")
    print(f"Extracted markdown (first 100 chars): {markdown_content[:100] if markdown_content else 'Empty'}")

    # Ensure we have content with better fallback handling
    if not markdown_content or len(markdown_content.strip()) < 100:
        print("Warning: Extracted markdown appears too short or empty. Using raw API response.")
        markdown_content = result.strip() if result else "Error: No content was generated."

    # The rest of your code remains the same...
    
    # Convert to HTML
    html_content = markdown_to_html(markdown_content)
    
    # Save to a file
    filename = f"seo_content_{primary_keyword.replace(' ', '_').lower()}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    # Return results as a dictionary with all necessary information
    return {
        'markdown': markdown_content,  # Changed from 'markdown_content' to 'markdown'
        'html': html_content,
        'filename': filename,
        'token_usage': token_usage
    }

def extract_markdown_content(response_text):
    """Improved extraction of markdown content from API responses"""
    if not response_text:
        return ""
        
    # If it's a dictionary or has 'content' key, extract that
    if isinstance(response_text, dict) and 'content' in response_text:
        response_text = response_text['content']
    
    # Rest of your extraction logic
    content_lines = []
    content_started = False
    
    # Process the response line by line
    for line in response_text.split("\n"):
        skip_line = False
        
        # Skip markdown code block identifiers
        if line.strip() == "markdown" or line.strip() == "":
            skip_line = True
        else:
            # Mark content started when we see a heading or paragraph
            if line.startswith("#") or len(line.strip()) > 0:
                content_started = True
        
        # Skip known postamble patterns - only if they're isolated lines and not part of content
        if (line.strip() == "Let me know if you need any revisions." or
            line.strip() == "Let me know if you would like any changes." or
            line.strip() == "Is there anything else you'd like me to help with?"):
            skip_line = True
        
        if content_started and not skip_line:
            content_lines.append(line)
    
    return "\n".join(content_lines).strip()

def markdown_to_html(markdown_content):
    """
    Convert markdown to HTML with improved support for tables and lists.
    
    Args:
        markdown_content (str): Markdown content to convert
        
    Returns:
        str: HTML content
    """
    try:
        import markdown
        from markdown.extensions import tables, fenced_code, attr_list, def_list, footnotes
        
        # Pre-process markdown to ensure proper list and table formatting
        processed_markdown = markdown_content
        
        # 1. Add empty line before lists that don't have them to ensure proper rendering
        processed_markdown = re.sub(r'([^\n])\n([\*\-\+]|\d+\.)\s', r'\1\n\n\2 ', processed_markdown)
        
        # 2. Fix table formatting issues
        # Ensure all table rows have a newline between them (crucial for table detection)
        processed_markdown = re.sub(r'\|\s*\n\s*\|', '|\n|', processed_markdown)
        
        # 3. Fix tables that don't have proper spacing in header separators
        # Find table header separators like |---|---| and ensure proper format
        processed_markdown = re.sub(r'\|([\s]*[-:]+[\s]*)\|', r'| \1 |', processed_markdown)
        
        # 4. Special handling for the exact table format provided in the example
        # This ensures proper formatting of the header separator row
        table_pattern = r'(\|[^\n]+\|)\n\|(\s*[-:]+\s*\|)+' 
        
        def reformat_table_headers(match):
            header_row = match.group(1)
            sep_row_original = match.group(0).split('\n')[1]
            
            # Count number of columns in the header row
            columns = header_row.count('|') - 1
            
            # Create a properly formatted separator row
            sep_row_new = '|' + '|'.join([' ----- ' for _ in range(columns)]) + '|'
            
            return header_row + '\n' + sep_row_new
                
        processed_markdown = re.sub(table_pattern, reformat_table_headers, processed_markdown)
        
        # Log the processed markdown for debugging
        logger.debug(f"Processed markdown before conversion:\n{processed_markdown[:200]}...")
        
        # Convert markdown to HTML with all necessary extensions enabled
        extensions = [
            'tables',             # Enable tables
            'fenced_code',        # Enable code blocks
            'attr_list',          # Enable attribute lists
            'def_list',           # Enable definition lists
            'nl2br',              # Convert newlines to <br>
            'sane_lists',         # Better list handling
            'footnotes',          # Enable footnotes
            'smarty',             # Smart typography (quotes, dashes)
            'md_in_html'          # Allow markdown inside HTML
        ]
        
        extension_configs = {
            'tables': {
                'use_align_attribute': True
            }
        }
        
        converted_html = markdown.markdown(
            processed_markdown,
            extensions=extensions,
            extension_configs=extension_configs
        )
        
        # Manual fallback for tables if the markdown extension fails
        if '<table>' not in converted_html and '|' in markdown_content and '-' in markdown_content:
            logger.debug("Table detection failed, applying manual table conversion")
            
            # Manual table parsing as fallback
            table_blocks = re.findall(r'(\|[^\n]+\|\n\|[-:\s\|]+\|\n(?:\|[^\n]+\|\n)+)', markdown_content)
            
            for table_block in table_blocks:
                logger.debug(f"Found table block that needs manual conversion: {table_block[:100]}...")
                
                lines = table_block.strip().split('\n')
                if len(lines) >= 3:  # Need at least header, separator, and one data row
                    html_table = '<table class="table table-bordered">\n<thead>\n<tr>\n'
                    
                    # Process header row
                    header_cells = [cell.strip() for cell in lines[0].split('|')[1:-1]]
                    for cell in header_cells:
                        html_table += f'<th>{cell}</th>\n'
                    
                    html_table += '</tr>\n</thead>\n<tbody>\n'
                    
                    # Process data rows
                    for line in lines[2:]:
                        if '|' not in line:
                            continue
                        
                        html_table += '<tr>\n'
                        cells = [cell.strip() for cell in line.split('|')[1:-1]]
                        for cell in cells:
                            html_table += f'<td>{cell}</td>\n'
                        html_table += '</tr>\n'
                    
                    html_table += '</tbody>\n</table>'
                    
                    # Replace the original table block with the HTML table
                    escaped_block = re.escape(table_block)
                    converted_html = converted_html.replace(table_block, html_table)
                    processed_markdown = processed_markdown.replace(table_block, html_table)
        
        # Wrap in HTML document with styling
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Generated Content</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #333; }}
                h2 {{ color: #444; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                h3 {{ color: #555; }}
                h4, h5, h6 {{ color: #666; }}
                code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 4px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }}
                blockquote {{ border-left: 4px solid #ddd; padding-left: 10px; color: #666; }}
                a {{ color: #0366d6; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                
                /* Table styling - enhanced for better display */
                table {{ 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin: 15px 0; 
                    border: 2px solid #ddd;
                    table-layout: fixed;
                }}
                th, td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: left;
                    word-wrap: break-word;
                }}
                th {{ 
                    background-color: #f2f2f2; 
                    font-weight: bold;
                    border-bottom: 2px solid #ddd;
                }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                tr:hover {{ background-color: #f5f5f5; }}
                
                /* List styling */
                ul, ol {{ padding-left: 25px; margin-bottom: 15px; }}
                li {{ margin-bottom: 5px; }}
                ul ul, ol ol, ul ol, ol ul {{ margin-bottom: 0; }}
                
                /* Image styling */
                img {{ max-width: 100%; height: auto; display: block; margin: 20px 0; }}
            </style>
        </head>
        <body>
            {converted_html}
        </body>
        </html>
        """
        
        # Log the HTML generation for debugging
        logger.debug("HTML generation completed successfully")
        
    except ImportError as e:
        logger.error(f"Error importing markdown library: {str(e)}")
        # Fallback if markdown library isn't available
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Generated Content</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
            </style>
        </head>
        <body>
            <pre>{markdown_content}</pre>
        </body>
        </html>
        """
    except Exception as e:
        logger.error(f"Error converting markdown to HTML: {str(e)}")
        # General error fallback
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Generated Content</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
            </style>
        </head>
        <body>
            <h1>Error converting markdown</h1>
            <p>There was an error converting the markdown to HTML. Please view the raw markdown instead:</p>
            <pre>{markdown_content}</pre>
        </body>
        </html>
        """
    
    return html
