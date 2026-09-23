"use client";

import { ListKit } from "@tiptap/extension-list";
import { TableKit } from "@tiptap/extension-table";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Code2,
  Eye,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  Link2,
  List,
  ListChecks,
  ListOrdered,
  Minus,
  Pencil,
  Quote,
  Redo2,
  Strikethrough,
  Table2,
  Underline,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { htmlToText, sanitizeNoteHtml } from "./html-content";

type RichTextEditorProps = {
  initialHtml: string;
  readOnly: boolean;
  onHtmlChange: (html: string) => void;
};

type ToolbarButtonProps = {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
};

function ToolbarButton({
  label,
  active = false,
  disabled = false,
  onClick,
  children,
}: ToolbarButtonProps) {
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="icon-sm"
      aria-label={label}
      aria-pressed={active}
      title={label}
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function ToolbarDivider() {
  return <span aria-hidden="true" className="mx-0.5 h-5 w-px bg-border" />;
}

function LinkToolbarButton({
  editor,
  disabled,
}: {
  editor: NonNullable<ReturnType<typeof useEditor>>;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");

  function openLinkEditor(nextOpen: boolean) {
    if (nextOpen) {
      setUrl(editor.getAttributes("link").href ?? "");
    }
    setOpen(nextOpen);
  }

  function applyLink(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = url.trim();
    if (!value) {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
    } else {
      editor.chain().focus().extendMarkRange("link").setLink({ href: value }).run();
    }
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={openLinkEditor}>
      <PopoverTrigger
        render={
          <Button
            type="button"
            variant={editor.isActive("link") ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Add or edit link"
            aria-pressed={editor.isActive("link")}
            title="Add or edit link"
            disabled={disabled}
            onMouseDown={(event) => event.preventDefault()}
          />
        }
      >
        <Link2 aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <PopoverHeader>
          <PopoverTitle>Link</PopoverTitle>
          <PopoverDescription>Use a secure web, mail, or relative URL.</PopoverDescription>
        </PopoverHeader>
        <form className="mt-4 space-y-3" onSubmit={applyLink}>
          <Input
            aria-label="Link URL"
            autoFocus
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm">
              Apply
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function RichTextToolbar({
  editor,
  onPreview,
}: {
  editor: NonNullable<ReturnType<typeof useEditor>>;
  onPreview: () => void;
}) {
  const [, forceUpdate] = useState(0);

  useEffect(() => {
    const update = () => forceUpdate((value) => value + 1);
    editor.on("selectionUpdate", update);
    editor.on("transaction", update);
    return () => {
      editor.off("selectionUpdate", update);
      editor.off("transaction", update);
    };
  }, [editor]);

  const disabled = !editor.isEditable;
  return (
    <div className="memory-editor__toolbar" role="toolbar" aria-label="Text formatting">
      <div className="memory-editor__toolbar-group">
        <ToolbarButton
          label="Heading 1"
          active={editor.isActive("heading", { level: 1 })}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        >
          <Heading1 aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton
          label="Heading 2"
          active={editor.isActive("heading", { level: 2 })}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        >
          <Heading2 aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton
          label="Heading 3"
          active={editor.isActive("heading", { level: 3 })}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        >
          <Heading3 aria-hidden="true" />
        </ToolbarButton>
      </div>
      <ToolbarDivider />
      <div className="memory-editor__toolbar-group">
        <ToolbarButton label="Bold" active={editor.isActive("bold")} disabled={disabled} onClick={() => editor.chain().focus().toggleBold().run()}>
          <Bold aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Italic" active={editor.isActive("italic")} disabled={disabled} onClick={() => editor.chain().focus().toggleItalic().run()}>
          <Italic aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Underline" active={editor.isActive("underline")} disabled={disabled} onClick={() => editor.chain().focus().toggleUnderline().run()}>
          <Underline aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Strikethrough" active={editor.isActive("strike")} disabled={disabled} onClick={() => editor.chain().focus().toggleStrike().run()}>
          <Strikethrough aria-hidden="true" />
        </ToolbarButton>
      </div>
      <ToolbarDivider />
      <div className="memory-editor__toolbar-group">
        <LinkToolbarButton editor={editor} disabled={disabled} />
        <ToolbarButton label="Inline code" active={editor.isActive("code")} disabled={disabled} onClick={() => editor.chain().focus().toggleCode().run()}>
          <Code2 aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Code block" active={editor.isActive("codeBlock")} disabled={disabled} onClick={() => editor.chain().focus().toggleCodeBlock().run()}>
          <span className="font-mono text-[0.65rem] font-bold">&lt;/&gt;</span>
        </ToolbarButton>
      </div>
      <ToolbarDivider />
      <div className="memory-editor__toolbar-group">
        <ToolbarButton label="Bulleted list" active={editor.isActive("bulletList")} disabled={disabled} onClick={() => editor.chain().focus().toggleBulletList().run()}>
          <List aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Numbered list" active={editor.isActive("orderedList")} disabled={disabled} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
          <ListOrdered aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Task list" active={editor.isActive("taskList")} disabled={disabled} onClick={() => editor.chain().focus().toggleTaskList().run()}>
          <ListChecks aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Blockquote" active={editor.isActive("blockquote")} disabled={disabled} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
          <Quote aria-hidden="true" />
        </ToolbarButton>
      </div>
      <ToolbarDivider />
      <div className="memory-editor__toolbar-group">
        <ToolbarButton label="Insert divider" disabled={disabled} onClick={() => editor.chain().focus().setHorizontalRule().run()}>
          <Minus aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Insert table" disabled={disabled} onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}>
          <Table2 aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Undo" disabled={disabled || !editor.can().undo()} onClick={() => editor.chain().focus().undo().run()}>
          <Undo2 aria-hidden="true" />
        </ToolbarButton>
        <ToolbarButton label="Redo" disabled={disabled || !editor.can().redo()} onClick={() => editor.chain().focus().redo().run()}>
          <Redo2 aria-hidden="true" />
        </ToolbarButton>
      </div>
      <span className="memory-editor__toolbar-spacer" />
      <Button type="button" variant="outline" size="sm" onClick={onPreview}>
        <Eye data-icon="inline-start" aria-hidden="true" />
        Preview
      </Button>
    </div>
  );
}

function RenderedNoteHtml({ html }: { html: string }) {
  return (
    <div
      className="memory-editor__content memory-editor__content--preview"
      dangerouslySetInnerHTML={{ __html: sanitizeNoteHtml(html) }}
    />
  );
}

export function RichTextEditor({
  initialHtml,
  readOnly,
  onHtmlChange,
}: RichTextEditorProps) {
  const initialContent = sanitizeNoteHtml(initialHtml) || "<p></p>";
  const onHtmlChangeRef = useRef(onHtmlChange);
  const [currentHtml, setCurrentHtml] = useState(() => sanitizeNoteHtml(initialHtml));
  const [preview, setPreview] = useState(readOnly);

  useEffect(() => {
    onHtmlChangeRef.current = onHtmlChange;
  }, [onHtmlChange]);

  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({
          bulletList: false,
          heading: { levels: [1, 2, 3] },
          listItem: false,
          listKeymap: false,
          orderedList: false,
        }),
        TableKit,
        ListKit,
      ],
      content: initialContent,
      editable: !readOnly,
      immediatelyRender: false,
      onUpdate: ({ editor: currentEditor }) => {
        const nextHtml = sanitizeNoteHtml(currentEditor.getHTML());
        setCurrentHtml(nextHtml);
        onHtmlChangeRef.current(nextHtml);
      },
    },
    [],
  );

  if (!editor) {
    return <div className="memory-editor__loading" aria-hidden="true" />;
  }

  if (readOnly || preview) {
    return (
      <div>
        {!readOnly ? (
          <div className="mb-4 flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={() => setPreview(false)}>
              <Pencil data-icon="inline-start" aria-hidden="true" />
              Edit
            </Button>
          </div>
        ) : null}
        <RenderedNoteHtml html={currentHtml} />
      </div>
    );
  }

  return (
    <div>
      <RichTextToolbar editor={editor} onPreview={() => setPreview(true)} />
      <EditorContent editor={editor} className={cn("memory-editor__content", "memory-editor__content--editable")} />
      <p className="mt-3 text-xs leading-5 text-muted-foreground">
        Rich text is saved as sanitized HTML. Use the preview to check the final note.
      </p>
    </div>
  );
}

export { htmlToText };
