import { useState } from "react";
import { api } from "./api";

type Preview = { text: string; timestamp: string; count: number };

export function ObservationTest({ notify, disabled }: { notify: (message: string) => void; disabled: boolean }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      setPreview(await api<Preview>("/webhook/observation-preview"));
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ count: number }>("/webhook/test-observation", "POST", undefined, { timeoutMs: 30000 });
      notify(`行情观察测试已发送，包含 ${result.count} 个标的；可在提醒中心查看结果`);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="observation-test">
      <h3>行情观察推送测试</h3>
      <p className="muted">先保存偏好设置，并在自选行情刷新报价。此处读取已保存的通知市场、最近行情和持仓；不调用 AI。休市或过期报价会标注，不会当作实时操作建议。</p>
      <button className="secondary" disabled={busy || disabled} onClick={() => void load()}>
        {busy ? "处理中…" : "预览当前行情观察"}
      </button>
      {error && <p className="hint" role="alert">{error}</p>}
      {preview && <>
        <p className="muted">共 {preview.count} 个标的。下方是默认可读正文；自定义模板仍按已保存的模板发送。发送时重新读取最新快照。</p>
        <textarea aria-label="行情观察推送预览" readOnly rows={10} value={preview.text} />
        <p className="muted">点击后立即发送一次测试，忽略定时窗口和静默设置，不占用正式日报名额。失败不自动重试，结果记入提醒中心。</p>
        <button className="secondary" disabled={busy || disabled} onClick={() => void send()}>发送行情观察测试</button>
      </>}
    </div>
  );
}
