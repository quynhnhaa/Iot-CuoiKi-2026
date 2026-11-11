import { useState } from 'react'

import { Icon } from '../components/Icon'
import { Alert, Field } from '../components/ui'
import { api, type LoginChallenge } from '../lib/api'
import { useAuth } from '../lib/auth'

type Stage = 'password' | 'totp' | 'recovery' | 'enroll' | 'saved-codes'

/** Bước nào thuộc lớp thứ nhất, bước nào thuộc lớp thứ hai. */
const SECOND_FACTOR: Stage[] = ['totp', 'recovery', 'enroll', 'saved-codes']

export function LoginPage() {
  const { signIn } = useAuth()
  const [stage, setStage] = useState<Stage>('password')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')

  // mfa_token sống rất ngắn và chỉ dùng cho bước hai, nên giữ trong state —
  // không ghi vào localStorage.
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [enrollment, setEnrollment] = useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [pendingToken, setPendingToken] = useState<string | null>(null)

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const submitPassword = () =>
    run(async () => {
      const challenge: LoginChallenge = await api.login(username, password)
      setMfaToken(challenge.mfa_token)
      setPassword('')
      if (challenge.stage === 'totp_required') {
        setStage('totp')
      } else {
        setEnrollment(await api.enroll(challenge.mfa_token))
        setStage('enroll')
      }
    })

  const submitTotp = () =>
    run(async () => {
      const token = await api.verifyTotp(mfaToken!, code)
      setCode('')
      await signIn(token.access_token)
    })

  const submitRecovery = () =>
    run(async () => {
      const token = await api.verifyRecoveryCode(mfaToken!, recoveryCode)
      setRecoveryCode('')
      await signIn(token.access_token)
    })

  const submitEnrollment = () =>
    run(async () => {
      const confirmed = await api.confirmEnrollment(mfaToken!, code)
      setCode('')
      setRecoveryCodes(confirmed.recovery_codes)
      setPendingToken(confirmed.access_token)
      setStage('saved-codes')
    })

  const onSecondFactor = SECOND_FACTOR.includes(stage)

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="sidebar-mark">
            <Icon name="pill" size={22} />
          </span>
          <div>
            <h1>Máy đếm và loại viên thuốc lỗi</h1>
            <p>Bảng quản lý mẻ đếm</p>
          </div>
        </div>

        <section className="card">
          <div className="card-body">
            <div className="auth-steps">
              <span className={`auth-step ${onSecondFactor ? 'done' : 'current'}`}>
                <span className="auth-step-dot">
                  {onSecondFactor ? <Icon name="check" size={11} /> : '1'}
                </span>
                Mật khẩu
              </span>
              <span className="auth-step-line" />
              <span className={`auth-step ${onSecondFactor ? 'current' : ''}`}>
                <span className="auth-step-dot">2</span>
                Mã xác thực
              </span>
            </div>

            {error && (
              <Alert variant="critical">
                <p>{error}</p>
              </Alert>
            )}

            {stage === 'password' && (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submitPassword()
                }}
              >
                <Field label="Tên đăng nhập">
                  <input
                    value={username}
                    autoComplete="username"
                    autoFocus
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </Field>
                <Field label="Mật khẩu">
                  <input
                    type="password"
                    value={password}
                    autoComplete="current-password"
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
                <button
                  type="submit"
                  className="btn block"
                  disabled={busy || !username || !password}
                  style={{ marginTop: 'var(--space-5)' }}
                >
                  {busy && <span className="spinner" />}
                  Tiếp tục
                </button>
                <p className="hint" style={{ marginTop: 'var(--space-3)' }}>
                  Sau bước này còn một lớp nữa: mã 6 số từ ứng dụng xác thực.
                </p>
              </form>
            )}

            {stage === 'totp' && (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submitTotp()
                }}
              >
                <Field
                  label="Mã xác thực"
                  hint="Mã 6 số đang hiện trong ứng dụng xác thực của bạn."
                  className="code-input"
                >
                  <input
                    value={code}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="000000"
                    autoFocus
                    onChange={(e) => setCode(e.target.value)}
                  />
                </Field>
                <button
                  type="submit"
                  className="btn block"
                  disabled={busy || code.length < 6}
                  style={{ marginTop: 'var(--space-5)' }}
                >
                  {busy && <span className="spinner" />}
                  Đăng nhập
                </button>
                <div style={{ marginTop: 'var(--space-4)', textAlign: 'center' }}>
                  <button type="button" className="btn-link" onClick={() => setStage('recovery')}>
                    Mất thiết bị? Dùng mã dự phòng
                  </button>
                </div>
              </form>
            )}

            {stage === 'recovery' && (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submitRecovery()
                }}
              >
                <Field label="Mã dự phòng" hint="Mỗi mã dự phòng chỉ dùng được một lần.">
                  <input
                    value={recoveryCode}
                    placeholder="XXXX-XXXX-XXXX-XXXX"
                    autoFocus
                    onChange={(e) => setRecoveryCode(e.target.value)}
                  />
                </Field>
                <button
                  type="submit"
                  className="btn block"
                  disabled={busy || !recoveryCode}
                  style={{ marginTop: 'var(--space-5)' }}
                >
                  {busy && <span className="spinner" />}
                  Đăng nhập
                </button>
                <div style={{ marginTop: 'var(--space-4)', textAlign: 'center' }}>
                  <button type="button" className="btn-link" onClick={() => setStage('totp')}>
                    Quay lại nhập mã thường
                  </button>
                </div>
              </form>
            )}

            {stage === 'enroll' && enrollment && (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  void submitEnrollment()
                }}
              >
                <h2>Ghi danh xác thực hai lớp</h2>
                <p className="hint" style={{ marginTop: 'var(--space-2)' }}>
                  Tài khoản này chưa bật lớp thứ hai. Thêm khoá dưới đây vào ứng dụng xác thực
                  (Google Authenticator, Aegis, 1Password…), rồi nhập mã nó sinh ra.
                </p>

                <pre className="secret-key" style={{ marginTop: 'var(--space-4)' }}>
                  {enrollment.secret.match(/.{1,4}/g)?.join(' ')}
                </pre>
                <details style={{ marginTop: 'var(--space-2)' }}>
                  <summary className="hint" style={{ cursor: 'pointer' }}>
                    Hoặc dán đường dẫn otpauth://
                  </summary>
                  <pre className="secret-uri" style={{ marginTop: 'var(--space-2)' }}>
                    {enrollment.otpauth_uri}
                  </pre>
                </details>

                <Field label="Mã xác thực" className="code-input">
                  <input
                    value={code}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    placeholder="000000"
                    onChange={(e) => setCode(e.target.value)}
                  />
                </Field>
                <button
                  type="submit"
                  className="btn block"
                  disabled={busy || code.length < 6}
                  style={{ marginTop: 'var(--space-5)' }}
                >
                  {busy && <span className="spinner" />}
                  Xác nhận và bật
                </button>
              </form>
            )}

            {stage === 'saved-codes' && (
              <div>
                <h2>Mã dự phòng</h2>
                <Alert variant="caution" icon="shield">
                  <p>
                    Lưu những mã này ở nơi an toàn <strong>ngay bây giờ</strong>. Chúng chỉ hiện một
                    lần, và mỗi mã dùng được một lần khi bạn mất thiết bị sinh mã.
                  </p>
                </Alert>
                <pre className="recovery-codes" style={{ marginTop: 'var(--space-4)' }}>
                  {recoveryCodes.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </pre>
                <button
                  className="btn block"
                  style={{ marginTop: 'var(--space-5)' }}
                  onClick={() => void signIn(pendingToken!)}
                >
                  Tôi đã lưu, vào hệ thống
                </button>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
