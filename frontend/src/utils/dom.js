// Utilidades DOM compartidas para evitar duplicación al construir vistas.

export function clearChildren(element) {
  if (!element) return;
  element.replaceChildren();
}

export function createElement(tag, options = {}, children = []) {
  const element = document.createElement(tag);

  if (options.className) {
    element.className = options.className;
  }
  if (options.text) {
    element.textContent = options.text;
  }
  if (options.type) {
    element.type = options.type;
  }
  if (options.attrs) {
    for (const [key, value] of Object.entries(options.attrs)) {
      element.setAttribute(key, String(value));
    }
  }
  if (options.style) {
    Object.assign(element.style, options.style);
  }
  if (options.onClick) {
    element.addEventListener('click', options.onClick);
  }

  for (const child of children) {
    if (child == null) continue;
    element.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }

  return element;
}
