"""Small read-only HTML tree, no script execution or third-party dependencies."""
from html.parser import HTMLParser


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children).strip()

    def all(self, **attrs):
        result = []
        for c in self.children:
            if isinstance(c, Node):
                if all(k in c.attrs and (v is None or c.attrs[k] == v) for k, v in attrs.items()):
                    result.append(c)
                result.extend(c.all(**attrs))
        return result

    def cls(self, name):
        return [n for n in self.all() if name in n.attrs.get('class', '').split()]


class Tree(HTMLParser):
    VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)
