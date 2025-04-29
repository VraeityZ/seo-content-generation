# SEO Content Generator

A tool for generating SEO-optimized markdown content from CORA reports using Claude AI.

## Features

- Parse CORA reports to extract SEO requirements
- Generate markdown content optimized for SEO
- Validate content against requirements
- Support for heading structure controls
- Streamlit web interface for ease of use

## Installation

1. Clone this repository:
   ```
   git clone <your-repository-url>
   cd SEO-Content-Generator
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

### Running the Streamlit App

Run the application with:

```
streamlit run app.py
```

This will start a local web server and open the application in your browser.

### Using the Application

1. Enter your Claude API key in the sidebar
2. Adjust heading controls if needed
3. Upload a CORA report Excel file
4. Click "Process CORA Report"
5. Review the generated content and validation results
6. Download the markdown file

## Git Usage Guide

### Initial Setup (One-time)

1. Install Git from [git-scm.com](https://git-scm.com/)
2. Configure your identity:
   ```
   git config --global user.name "Your Name"
   git config --global user.email "your.email@example.com"
   ```
3. Create a GitHub account at [github.com](https://github.com/)
4. Create a new repository on GitHub
5. Initialize your local repository:
   ```
   cd c:\Users\hunte\Desktop\Tool test\SDK
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/your-repo-name.git
   git push -u origin main
   ```

### Daily Git Workflow

1. Make changes to your code
2. Stage your changes:
   ```
   git add .
   ```
3. Commit your changes:
   ```
   git commit -m "Brief description of changes"
   ```
4. Push to GitHub:
   ```
   git push
   ```

### Viewing Changes

To see what files have changed:
```
git status
```

To see specific changes in files:
```
git diff
```

### Getting Updates

If working on multiple computers:
```
git pull
```

## Project Structure

- `main.py` - Core functions for parsing CORA reports and generating content
- `app.py` - Streamlit web interface
- `requirements.txt` - Project dependencies
- `output_markdown/` - Directory for generated markdown files
