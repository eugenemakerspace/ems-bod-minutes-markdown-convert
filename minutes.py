from mistletoe import Document
from mistletoe.block_token import Paragraph
from mistletoe.ast_renderer import ASTRenderer
from mistletoe.ast_renderer import get_ast
import json
import re
import sys

def logmsg(msg):
    print(msg, file=sys.stderr)

def process_keywords(textw):
    """Parses the @motion line into components"""
    text = textw.strip()
    pattern = r"^@([a-zA-Z]+):?\s*(.*)"
    match = re.fullmatch(pattern, text)
    result = None

    if not match:
        logmsg(f"No @keyword in {text}")
        return None
    keyword = match.group(1).lower()
    content = match.group(2).strip()
    logmsg(f"Matched keyword: {keyword}, content: {content}")

    if keyword == "motion":
        result = parse_motion(content)
    elif keyword == "action":
        result = parse_action(content)
    return result

def split_namevalue(content):
    pattern = r"[:,\.]"
    logmsg(f"split_namevalue, content: {content}")

    name, *rest = [p.strip() for p in re.split(pattern, content)]
    value = rest[0] if rest else ""
    return [name, value]

def parse_motion(content):
    # input is something like: 
    # Sam, Approve the agenda as presented. Seconded: Andrew. Passes, approved unanimously.
    # First split into sentences (name/value pairs)
    results = [p.strip() for p in content.split(".", maxsplit=3)]
    logmsg(f"got results: {len(results)}")
    motion_part, second_part, outcome_part, *rest = results

    mover, motion_text = split_namevalue(motion_part)
    _, seconder = split_namevalue(second_part)
    passfail, outcome_detail = split_namevalue(outcome_part)

    template_node = {
        "type": "Paragraph",
        "children": [{
            "type": "RawText",
            "content": f"{{{{Motion|{mover}|{motion_text}|{seconder}|{outcome_detail}}}}}"
        }]
    }
    return template_node

def parse_action(content):

    name, *rest = content.split(maxsplit=1)
    action = rest[0] if rest else ""

    words = action.split(maxsplit=1)
    if words and words[0].lower() in ["will", "to"]:
        action = words[1] if len(words) > 1 else ''

    # the @action wiki macro expands to {name} will {action}
    # so we trim off words like "will", "to"
    # {{action|Sam|will open a PO Box for the maker space.}}
    template_node = {
        "type": "Paragraph",
        "children": [{
            "type": "RawText",
            "content": f"{{{{action|{name}|{action}}}}}"
        }]
    }
    return template_node

def process_ast(ast):
    """Recursively transform the AST"""
    new_children = []
    for node in ast["children"]:
        if node["type"] == "Paragraph":
            para_text = "".join([c["content"] for c in node["children"] if c["type"] == "RawText"])
            result_node = process_keywords(para_text)
            if result_node:
                logmsg(f"get extracted keyword ast node, text: {para_text}")
                new_children.append(result_node)
            else:
                new_children.append(node)
        elif "children" in node:
          new_children.append(process_ast(node))
        else:
          new_children.append(node)
    ast["children"] = new_children
    return ast

def examine_ast(ast):
  logmsg(json.dumps(ast, indent=2))  

def render_markdown_document(ast):
    lines = []
    for node in ast["children"]:
        lines.append(render_markdown_node(node, 0))

    return "\n".join(lines)

def render_markdown_node(node, indent_level=0):
    indent = '  ' * indent_level  # 2 spaces per level
    if "children" in node:
        content = ''.join(render_markdown_node(child, indent_level) for child in node["children"])
    elif "content" in node:
        content = node["content"]
    else:
        logmsg("no content or children?")
        logmsg(node)
        return ""

    if node["type"] == "Heading":
        return f"{'=' * node['level']}{content}{'=' * node['level']}\n"
    elif node["type"] == "Paragraph":
        return f"{content}"
    elif node["type"] == "List":
        node_str = ""
        if indent_level > 0:
            node_str += "\n"
        node_str += ''.join(render_markdown_node(item, indent_level) for item in node["children"])
        return node_str
    elif node["type"] == "ListItem":
        item_content = ''.join(render_markdown_node(child, indent_level + 1) for child in node["children"])
        # Handle multi-paragraph list items or nested lists
        if '\n' in item_content.strip():
            return f"*{'*' * indent_level} {item_content}"
        return f"*{'*' * indent_level} {item_content.strip()}\n"
    elif node["type"] == "Strong":
        return f"**{content}**"
    elif node["type"] == "Emphasis":
        return f"*{content}*"
    elif node["type"] == "InlineCode":
        return f"`{content}`"
    elif node["type"] == "CodeFence":
        return f"```\n{content}```\n\n"
    elif node["type"] == "Link":
        return f"[{node['target']} {content}]"
    elif node["type"] == "Image":
        return f"![{content}]({node['src']})"
    elif node["type"] == "LineBreak":
        return "  \n"
    else:
        return content  # fallback for plain text or unhandled types


def render_ast_as_lines(ast):
    """Render the AST back to markdown"""
    lines = []
    for node in ast["children"]:
        if node["type"] == "Heading":
            level = node["level"]
            text = "".join(c["content"] for c in node["children"])
            lines.append(f"{'=' * level}{text}{'=' * level}")
        elif node["type"] == "Paragraph":
            text = "".join(c["content"] for c in node["children"])
            lines.append(text)
        elif node["type"] == "List":
            lines.extend(render_ast_as_lines(node))
        elif node["type"] == "ListItem":
            logmsg("ListItem")
            logmsg(node)
            lines.extend(render_ast_as_lines(node))
        else:
            logmsg(f"render didn't handle type: {node['type']}")  # could expand for other types, code blocks, etc.
        lines.append("")  # blank line for spacing
    return lines

def convert_file(input_file):
    with open(input_file, "r") as f:
        markdown = f.read()

    node = {}
    token = Document(markdown)
    ast = get_ast(token)
    modified_ast = process_ast(ast)

    with ASTRenderer() as renderer:
      new_markdown = render_markdown_document(modified_ast)
      return new_markdown

# Run the conversion
def main():
    if len(sys.argv) < 2:
        print("Usage: python minutes.py <filename>", file=sys.stderr)
        sys.exit(1)
    infile = sys.argv[1]
    output = convert_file(infile)
    print(output)

if __name__ == "__main__":
    main()
