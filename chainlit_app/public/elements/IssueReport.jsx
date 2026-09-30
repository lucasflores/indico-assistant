// The report form (spec 021, contracts/panel.md). The chat server drew it with its props; Send and Cancel call
// back with callAction. It is not drawn again after the panel reloads on another page (spec edge case).
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useState } from "react"

const KINDS = [["bug", "Bug"], ["feature", "Feature idea"], ["wrong_answer", "Wrong or poor answer"]]
const TEXT_MAX = 5000
const FAILED = "The report could not be sent, so please try again shortly."

export default function IssueReport() {
  const [kind, setKind] = useState(props.category || "")
  const [text, setText] = useState(props.text || "")
  const [attach, setAttach] = useState(!!props.can_attach)
  // "sent" is kept in the element's props (updateElement): Chainlit redraws the messages after a new chat's first
  // action, and local state alone came back as an empty draft (found live)
  const [state, setState] = useState(props.sent ? "sent" : "draft") // draft | sending | sent | error
  const [result, setResult] = useState(props.sent || null)
  const busy = state === "sending"

  async function send() {
    setState("sending") // a second click does nothing; the server's form key guards it too (R8)
    let res = null
    try {
      res = (await callAction({
        name: "report_submit",
        payload: { form_key: props.form_key, category: kind, text, attach: !!props.can_attach && attach,
                   answer_id: props.answer_id },
      }))?.response
    } catch (e) { /* said below */ }
    if (res && res.ok) {
      const sent = { report_id: res.report_id, url: res.url }
      updateElement({ ...props, sent })
      setResult(sent)
      setState("sent")
    } else {
      setResult({ message: (res && res.message) || FAILED })
      setState("error") // the text stays, to send again
    }
  }

  if (state === "sent") {
    return (
      <div data-issue="sent" role="status" aria-live="polite" className="p-3 border rounded-md text-sm">
        Report #{result.report_id} sent. <a href={result.url} className="underline">See your reports</a>
      </div>
    )
  }
  return (
    <div data-issue-report={props.form_key} className="flex flex-col gap-2 p-3 border rounded-md">
      <div role="group" aria-label="Kind of problem" className="flex flex-wrap gap-1">
        {KINDS.map(([k, label]) => (
          <Button key={k} data-issue={`kind-${k}`} size="sm" aria-pressed={kind === k} disabled={busy}
                  variant={kind === k ? "default" : "outline"} onClick={() => setKind(k)}>{label}</Button>
        ))}
      </div>
      <Textarea data-issue="text" aria-label="What happened?" placeholder="What happened?" maxLength={TEXT_MAX}
                value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />
      {props.can_attach && (
        <Label className="flex items-center gap-2 font-normal">
          <Checkbox data-issue="attach" checked={attach} disabled={busy} onCheckedChange={(v) => setAttach(!!v)} />
          Attach this conversation
        </Label>
      )}
      <div role="status" aria-live="polite" className="text-sm text-destructive">
        {state === "error" ? result.message : ""}
      </div>
      <div className="flex gap-2">
        <Button data-issue="send" disabled={busy || !kind || !text.trim()} onClick={send}>
          {busy ? "Sending…" : "Send report"}
        </Button>
        <Button data-issue="cancel" variant="ghost" disabled={busy}
                onClick={() => callAction({ name: "report_cancel", payload: { form_key: props.form_key } })}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
