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

# Motion grammar (keyword-anchored, NOT period-positional):
#   <mover>, <motion text>. Seconded: <seconder>. <result>: <outcome>.
# The motion text is matched non-greedily up to "Seconded:", so it may contain
# any number of sentences/periods/commas without shifting the other fields.
MOTION_RE = re.compile(
    r"^\s*(?P<mover>[^,]+?)\s*,\s*(?P<text>.+?)\s*\.?\s*"
    r"Seconded\s*:?\s*(?P<seconder>.+?)\s*\.?\s*"
    r"(?P<result>Passes|Fails|Carried|Tabled|Withdrawn|Defeated)\b\s*:?\s*"
    r"(?P<outcome>.+?)\s*\.?\s*$",
    re.IGNORECASE,
)

def parse_motion(content):
    # input is something like:
    # Sam, Approve the agenda as presented. Seconded: Andrew. Passes: approved unanimously.
    match = MOTION_RE.match(content)
    if not match:
        logmsg(f"WARNING: could not parse @motion, leaving raw text in place: {content!r}")
        return None

    mover = match.group("mover").strip()
    motion_text = match.group("text").strip().rstrip(".").strip()
    seconder = match.group("seconder").strip()
    result = match.group("result").strip().lower()
    outcome = match.group("outcome").strip().rstrip(".").strip()
    logmsg(f"Parsed motion: mover={mover!r} second={seconder!r} result={result!r} outcome={outcome!r}")

    template_node = {
        "type": "Paragraph",
        "children": [{
            "type": "RawText",
            "content": (
                f"'''Motion&#58;''' {mover} moved that the EMS Board of Directors shall: {motion_text}."
                f"<br>Seconded by {seconder}. '''Motion {result}''', {outcome}."
            )
        }]
    }
    return template_node

def parse_action(content):
    # input is something like:  Thomas, figure out a cost structure for workshops
    # Authors write "Name, action"; older usage was "Name action". Prefer the
    # comma split so a trailing comma never gets stuck onto the name.
    content = content.strip()
    if "," in content:
        name, action = content.split(",", 1)
    else:
        name, _, action = content.partition(" ")
    name = name.strip().rstrip(".,").strip()
    action = action.strip()

    # the @action wiki macro expands to "{name} will {action}", so trim a
    # leading "will"/"to" to avoid "Sam will will open a PO Box".
    words = action.split(maxsplit=1)
    if words and words[0].lower() in ["will", "to"]:
        action = words[1] if len(words) > 1 else ''

    if not name or not action:
        logmsg(f"WARNING: could not parse @action, leaving raw text in place: {content!r}")
        return None

    logmsg(f"Parsed action: name={name!r} action={action!r}")
    template_node = {
        "type": "Paragraph",
        "children": [{
            "type": "RawText",
            "content": f"{{{{action|{name}|{action}}}}}"
        }]
    }
    return template_node

def flatten_text(node):
    """Recursively collect all text in a node, including the content of
    EscapeSequence tokens (e.g. Google Docs exports a leading bullet as "\\-")."""
    if node.get("type") == "RawText":
        return node.get("content", "")
    return "".join(flatten_text(c) for c in node.get("children", []) or [])

def process_ast(ast):
    """Recursively transform the AST"""
    new_children = []
    for node in ast["children"]:
        if node["type"] == "Paragraph":
            full_text = flatten_text(node).strip()
            # A keyword line authored as a bullet may arrive as a paragraph when
            # Google Docs escapes the marker ("\- @action ..."). Detect a leading
            # "-"/"*" marker so we can re-bullet the result.
            marker_match = re.match(r"^[-*]\s+(.*)$", full_text, re.DOTALL)
            keyword_text = marker_match.group(1) if marker_match else full_text
            result_node = process_keywords(keyword_text)
            if result_node:
                logmsg(f"get extracted keyword ast node, text: {keyword_text}")
                if marker_match:
                    # originated from a (possibly escaped) bullet -> emit a list item
                    result_node = {"type": "List", "children": [
                        {"type": "ListItem", "children": [result_node]}]}
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
    # Separate top-level blocks with a blank line. MediaWiki only starts a new
    # paragraph on a blank line, so single-newline-joined blocks would otherwise
    # collapse into one paragraph (lost line breaks between prose/quotes/etc).
    blocks = []
    for node in ast["children"]:
        rendered = render_markdown_node(node, 0).rstrip("\n")
        if rendered:
            blocks.append(rendered)
    return "\n\n".join(blocks) + "\n"

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
        # Join block children with a single newline (never a blank line, which
        # would break the list), so consecutive loose paragraphs don't glue
        # together (e.g. "...x9Only two members..."). Nested lists already
        # carry their own leading newline.
        item_content = ""
        for child in node["children"]:
            piece = render_markdown_node(child, indent_level + 1)
            if not piece:
                continue
            if item_content and not item_content.endswith("\n") and not piece.startswith("\n"):
                item_content += "\n"
            item_content += piece
        if not item_content.strip():
            return ""  # drop empty bullets (e.g. a stray "* " in the source)
        # Handle multi-paragraph list items or nested lists. Ensure the item
        # ends in a newline so a trailing loose paragraph can't glue the next
        # sibling bullet onto it (e.g. "...platform fees* Member Matters:").
        if '\n' in item_content.strip():
            if not item_content.endswith("\n"):
                item_content += "\n"
            return f"*{'*' * indent_level} {item_content}"
        return f"*{'*' * indent_level} {item_content.strip()}\n"
    elif node["type"] == "Strong":
        return f"'''{content}'''"
    elif node["type"] == "Emphasis":
        return f"''{content}''"
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

def lint_output(text):
    """Scan the generated wikitext for things that usually mean a transform
    was missed. Returns a list of human-readable issue strings."""
    issues = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if re.search(r"\*\*[^*\s].*?\*\*", line):
            issues.append(f"line {i}: leftover markdown bold (**...**) — should be '''...''': {stripped}")
        if re.search(r"(?<!\!)\[[^\]]+\]\([^)]+\)", line):
            issues.append(f"line {i}: leftover markdown link [text](url): {stripped}")
        if re.fullmatch(r"\*+", stripped):
            issues.append(f"line {i}: empty list item")
        if re.search(r"[^\s*]\*+\s", line):
            issues.append(f"line {i}: possible bullet glued to preceding text: {stripped}")
        if re.search(r"@(motion|action)\b", line, re.IGNORECASE):
            issues.append(f"line {i}: unconverted @keyword (parse failed?): {stripped}")
    return issues

# Run the conversion
def main():
    if len(sys.argv) < 2:
        print("Usage: python minutes.py <filename>", file=sys.stderr)
        sys.exit(1)
    infile = sys.argv[1]
    output = convert_file(infile)
    print(output)

    issues = lint_output(output)
    if issues:
        logmsg(f"\nLINT: {len(issues)} issue(s) found in output — review before pasting to the wiki:")
        for issue in issues:
            logmsg(f"  - {issue}")
    else:
        logmsg("\nLINT: no issues found.")

if __name__ == "__main__":
    main()
