import MarkdownIt from 'markdown-it';

// Release notes are remote content. Keep raw HTML disabled and the parser's URL validation enabled.
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
markdown.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index].attrSet('target', '_blank');
  tokens[index].attrSet('rel', 'noopener noreferrer');
  return renderer.renderToken(tokens, index, options);
};

export function renderReleaseNotes(source: string): string {
  return markdown.render(source);
}
