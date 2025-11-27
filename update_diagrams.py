#!/usr/bin/env python3
"""
Replace mermaid diagrams with generated PNG images in index.html
"""
import re

# Read the HTML file
with open('index.html', 'r') as f:
    html = f.read()

# Define replacements for each diagram
replacements = [
    {
        'title': 'Microsoft Copilot Stack Architecture',
        'image': 'assets/diagrams/01-microsoft-copilot-stack.png',
        'alt': 'Microsoft Copilot Stack Architecture Diagram'
    },
    {
        'title': 'Advanced RAG Architecture (Production-Grade)',
        'image': 'assets/diagrams/02-rag-architecture.png',
        'alt': 'Advanced RAG Architecture Diagram'
    },
    {
        'title': 'Multi-Agent Orchestration Pattern (AutoGen Framework)',
        'image': 'assets/diagrams/03-multi-agent-orchestration.png',
        'alt': 'Multi-Agent Orchestration System Diagram'
    },
    {
        'title': 'Production-Ready Deployment Stack (Azure)',
        'image': 'assets/diagrams/04-production-deployment-azure.png',
        'alt': 'Production Deployment Stack on Azure'
    }
]

# Function to create image HTML
def create_image_html(image_path, alt_text):
    return f'''<img src="{image_path}" alt="{alt_text}" style="width: 100%; max-width: 1200px; height: auto; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">'''

# Replace each mermaid diagram
for rep in replacements:
    # Pattern to match: <h3>TITLE</h3>\n<div class="diagram-container">\n<div class="mermaid">...content...</div>\n</div>
    # We'll search for the title, then find and replace the mermaid container that follows

    title_pattern = re.escape(rep['title'])

    # Find the section with this title
    pattern = rf'(<h3[^>]*>{title_pattern}</h3>\s*<div class="diagram-container">)\s*<div class="mermaid">.*?</div>\s*(</div>)'

    replacement = rf'\1\n                    {create_image_html(rep["image"], rep["alt"])}\n                \2'

    html = re.sub(pattern, replacement, html, flags=re.DOTALL)
    print(f"✅ Replaced diagram: {rep['title']}")

# Write the updated HTML
with open('index.html', 'w') as f:
    f.write(html)

print("\n✅ Successfully updated index.html with image diagrams!")
print("📊 Replaced 4 mermaid diagrams with PNG images")
