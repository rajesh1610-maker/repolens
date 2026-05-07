/**
 * Tiny markdown renderer for AI digests.
 *
 * The digest format is constrained by the system prompt to a narrow
 * subset (H2 headings, bullet lists, paragraphs, inline `code`,
 * **bold**, *italic*) — pulling in `react-markdown` + `remark-gfm`
 * would add ~120 KB of deps to render that. This handles the subset
 * we actually emit, escapes everything else as plain text, and is
 * easy to reason about.
 *
 * Anything weirder than the supported subset (tables, images, raw
 * HTML) the validator already flags as a warning, so the user sees
 * the literal text rather than a silently broken render.
 */

import { Fragment, type ReactNode } from "react";

export function DigestMarkdown({ source }: { source: string }) {
  const blocks = parseBlocks(source.replace(/\r\n/g, "\n").trim());
  return (
    <div className="space-y-5 text-sm text-zinc-200 leading-relaxed">
      {blocks.map((b, i) => (
        <Fragment key={i}>{renderBlock(b)}</Fragment>
      ))}
    </div>
  );
}

type Block =
  | { kind: "h2"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "p"; text: string };

function parseBlocks(md: string): Block[] {
  const lines = md.split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const h2 = /^##\s+(.+?)\s*$/.exec(line);
    if (h2) {
      out.push({ kind: "h2", text: h2[1] });
      i++;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ""));
        i++;
      }
      out.push({ kind: "ul", items });
      continue;
    }
    // Paragraph: collect until blank line or block boundary.
    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^##\s+/.test(lines[i]) &&
      !/^[-*]\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    out.push({ kind: "p", text: para.join(" ") });
  }
  return out;
}

function renderBlock(block: Block): ReactNode {
  if (block.kind === "h2") {
    return (
      <h2 className="text-base font-semibold text-white border-b border-zinc-800 pb-2">
        {block.text}
      </h2>
    );
  }
  if (block.kind === "ul") {
    return (
      <ul className="list-disc pl-5 space-y-1.5 marker:text-zinc-600">
        {block.items.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>
    );
  }
  return <p>{renderInline(block.text)}</p>;
}

/**
 * Inline parser — handles `code`, **bold**, *italic*, and PR refs (#123).
 * Intentionally NOT recursive (no nested formatting). The digest format
 * is plain enough that this is fine.
 */
function renderInline(text: string): ReactNode {
  // Tokenize on ` … `, ** … **, * … *, and #123 patterns.
  const tokens: ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|#\d+)/g;
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIndex) {
      tokens.push(text.slice(lastIndex, m.index));
    }
    const matched = m[0];
    if (matched.startsWith("`")) {
      tokens.push(
        <code
          key={key++}
          className="px-1 py-0.5 rounded bg-zinc-800 text-zinc-200 font-mono text-[12px]"
        >
          {matched.slice(1, -1)}
        </code>
      );
    } else if (matched.startsWith("**")) {
      tokens.push(
        <strong key={key++} className="font-semibold text-white">
          {matched.slice(2, -2)}
        </strong>
      );
    } else if (matched.startsWith("*")) {
      tokens.push(
        <em key={key++} className="italic">
          {matched.slice(1, -1)}
        </em>
      );
    } else {
      // PR/issue ref like #123
      tokens.push(
        <span key={key++} className="text-teal-400 font-medium">
          {matched}
        </span>
      );
    }
    lastIndex = m.index + matched.length;
  }
  if (lastIndex < text.length) {
    tokens.push(text.slice(lastIndex));
  }
  return tokens.length === 0 ? text : tokens;
}
