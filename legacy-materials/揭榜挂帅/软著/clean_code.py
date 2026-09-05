import tokenize
import io
import sys

def clean_python_code(source):
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    modified_tokens = []
    i = 0
    depth = 0
    while i < len(tokens):
        t = tokens[i]
        
        # Track bracket depth
        if t.string in ('(', '[', '{'):
            depth += 1
        elif t.string in (')', ']', '}'):
            depth -= 1
            
        # 1. Skip comments
        if t.type == tokenize.COMMENT:
            i += 1
            continue
            
        # 2. Skip docstrings
        if t.type == tokenize.STRING:
            if t.string.startswith('"""') or t.string.startswith("'''"):
                # Find the last non-newline/non-indent token
                prev_t = None
                for idx in range(len(modified_tokens) - 1, -1, -1):
                    pt = modified_tokens[idx]
                    if pt.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                        prev_t = pt
                        break
                
                is_docstring = False
                if depth == 0:
                    if prev_t is None or prev_t.string in (':', ''):
                        is_docstring = True
                        
                if is_docstring:
                    i += 1
                    while i < len(tokens) and tokens[i].type in (tokenize.NL, tokenize.NEWLINE):
                        i += 1
                    continue
        
        modified_tokens.append(t)
        i += 1
        
    # Reconstruct the code using 2-tuples to avoid alignment backslashes
    reconstructed = tokenize.untokenize([(t.type, t.string) for t in modified_tokens])
    
    # Split into lines and strip empty lines
    lines = []
    for line in reconstructed.splitlines():
        if line.strip():
            lines.append(line)
            
    return "\n".join(lines)

def main():
    source_path = 'c:/Users/mioba/Desktop/大二春/揭榜挂帅/软著/main_inspection_system_v4.py'
    output_path = 'c:/Users/mioba/Desktop/大二春/揭榜挂帅/软著/main_inspection_system_v4_compliance.py'
    
    with open(source_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
        
    cleaned_code = clean_python_code(source_code)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_code)
    print("Success: Compliance file generated successfully!")

if __name__ == '__main__':
    main()
