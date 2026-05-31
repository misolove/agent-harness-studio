import React from 'react';

function renderInlineMarkdown(text) {
  const parts = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={parts.length}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(<code key={parts.length}>{token.slice(1, -1)}</code>);
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function parseMarkdownTable(lines, startIndex) {
  const header = lines[startIndex];
  const divider = lines[startIndex + 1];
  if (!header?.includes("|") || !divider?.match(/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/)) {
    return null;
  }

  const tableLines = [header, divider];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    tableLines.push(lines[index]);
    index += 1;
  }

  const splitRow = (line) => line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());

  return {
    headers: splitRow(tableLines[0]),
    rows: tableLines.slice(2).map(splitRow),
    nextIndex: index,
  };
}

function formatSessionDate(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    const millis = value > 1000000000000 ? value : value * 1000;
    const date = new Date(millis);
    return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 10);
  }
  const text = String(value);
  const numeric = Number(text);
  if (!Number.isNaN(numeric) && text.trim() !== "") {
    return formatSessionDate(numeric);
  }
  return text.slice(0, 10);
}

function MarkdownContent({ text }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    const table = parseMarkdownTable(lines, index);
    if (table) {
      blocks.push(
        <div className="md-table-wrap" key={blocks.length}>
          <table className="md-table">
            <thead>
              <tr>{table.headers.map((cell, i) => <th key={i}>{renderInlineMarkdown(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {table.headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInlineMarkdown(row[cellIndex] || "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      index = table.nextIndex;
      continue;
    }

    if (trimmed.startsWith("### ")) {
      blocks.push(<h4 key={blocks.length}>{renderInlineMarkdown(trimmed.slice(4))}</h4>);
      index += 1;
      continue;
    }

    if (trimmed.startsWith("## ")) {
      blocks.push(<h3 key={blocks.length}>{renderInlineMarkdown(trimmed.slice(3))}</h3>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={blocks.length}>
          {items.map((item, i) => <li key={i}>{renderInlineMarkdown(item)}</li>)}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={blocks.length}>
          {items.map((item, i) => <li key={i}>{renderInlineMarkdown(item)}</li>)}
        </ol>
      );
      continue;
    }

    if (trimmed === "---") {
      blocks.push(<hr key={blocks.length} />);
      index += 1;
      continue;
    }

    blocks.push(<p key={blocks.length}>{renderInlineMarkdown(trimmed)}</p>);
    index += 1;
  }

  return <div className="markdown-content">{blocks}</div>;
}

export default MarkdownContent;
export { renderInlineMarkdown, parseMarkdownTable, formatSessionDate };
