// The message composer: type a line and send it in-character (IC) or
// out-of-character (OOC). Both persist to the timeline via the room.

"use client";

import { useState } from "react";

type Channel = "ic" | "ooc";

export default function Composer({
  onChat,
  onOoc,
  disabled,
}: {
  onChat: (body: string) => void;
  onOoc: (body: string) => void;
  disabled?: boolean;
}) {
  const [channel, setChannel] = useState<Channel>("ic");
  const [text, setText] = useState("");

  function send() {
    const body = text.trim();
    if (!body) return;
    if (channel === "ic") onChat(body);
    else onOoc(body);
    setText("");
  }

  return (
    <div className="border-t border-stone-800 p-3">
      <div className="mb-2 flex gap-1 text-xs">
        {(["ic", "ooc"] as const).map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setChannel(c)}
            className={`rounded px-2 py-1 font-medium ${
              channel === c
                ? "bg-amber-700 text-amber-50"
                : "bg-stone-800 text-stone-400 hover:text-stone-200"
            }`}
          >
            {c === "ic" ? "In character" : "Out of character"}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={disabled}
          placeholder={
            channel === "ic" ? "Speak or act in character…" : "Aside to the table…"
          }
          className="flex-1 rounded bg-stone-800 px-3 py-2 text-sm text-stone-100 placeholder:text-stone-500 focus:outline-none focus:ring-1 focus:ring-amber-600 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={send}
          disabled={disabled}
          className="rounded bg-amber-700 px-4 py-2 text-sm font-medium text-amber-50 hover:bg-amber-600 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
