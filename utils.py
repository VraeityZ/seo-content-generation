import os
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
OUTPUT_DIR = "output"

def ensure_output_directory():
    """
    Ensure the output directory exists.
    
    Returns:
        str: Path to the output directory
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR

def save_markdown_to_file(markdown_str, keyword):
    """
    Saves markdown content to a file.
    
    Args:
        markdown_str (str): Markdown content to save
        keyword (str): Primary keyword for filename
        iteration (int): Iteration number for versioning
        
    Returns:
        str: Path to the saved file
    """
    try:
        os.makedirs("output", exist_ok=True)
        
        # Clean keyword for filename
        clean_keyword = keyword.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"seo_content_{clean_keyword}_{timestamp}.md"
        
        file_path = os.path.join("output", filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(markdown_str)
        
        return file_path
    
    except Exception as e:
        st.error(f"Error saving markdown to file: {str(e)}")
        return None
def save_json_to_file(data, filename):
    """
    Save data as JSON to a file.
    
    Args:
        data: Data to save as JSON
        filename (str): Filename to save to
        
    Returns:
        str: Path to the saved file
    """
    try:
        ensure_output_directory()
        file_path = os.path.join(OUTPUT_DIR, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"Saved JSON to: {file_path}")
        return file_path
    
    except Exception as e:
        logger.error(f"Error saving JSON to file: {str(e)}")
        return None
