import React, { useEffect, useState } from "https://esm.sh/react@18.3.1?dev";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client?dev&deps=react@18.3.1";
import htm from "https://esm.sh/htm@3.1.1";
import {
  HashRouter,
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "https://esm.sh/react-router-dom@6.30.1?dev&deps=react@18.3.1,react-dom@18.3.1";

const html = htm.bind(React.createElement);
const API_BASE = "/api";
const TOKEN_KEY = "cambridge-cofounder-token";

const SKILLS = ["Engineering", "Product", "Business"];
const COMMITMENT_LEVELS = ["Exploring", "Part-time", "Serious"];
const LOOKING_FOR_OPTIONS = ["Technical", "Non-technical", "Either"];

function loadToken() {
  return window.localStorage.getItem(TOKEN_KEY);
}

function saveToken(token) {
  if (!token) {
    window.localStorage.removeItem(TOKEN_KEY);
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}

async function apiFetch(path, options = {}, token) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Something went wrong" }));
    throw new Error(error.detail || "Something went wrong");
  }

  return response.json();
}

function createApiClient(token, onUnauthorized) {
  return async (path, options = {}) => {
    try {
      return await apiFetch(path, options, token);
    } catch (error) {
      const message = String(error.message).toLowerCase();
      if (message.includes("session expired") || message.includes("authentication required")) {
        onUnauthorized();
      }
      throw error;
    }
  };
}

function Pill({ children, tone = "default" }) {
  return html`<span className=${`pill ${tone}`}>${children}</span>`;
}

function Avatar({ src, name, size = "medium" }) {
  return html`<img className=${`avatar avatar-${size}`} src=${src} alt=${name} />`;
}

function Header({ user, onLogout }) {
  const location = useLocation();
  const navItems = [
    { to: "/feed", label: "Feed" },
    { to: "/requests", label: "Requests" },
    { to: "/connections", label: "Connections" },
    { to: "/profile", label: "My profile" },
  ];

  return html`
    <header className="topbar">
      <div>
        <div className="brand">Cambridge Co-founder Platform</div>
        <div className="brand-subtle">Verified Cambridge builders only</div>
      </div>
      <nav className="nav-links">
        ${navItems.map(
          (item) => html`
            <${Link}
              className=${location.pathname === item.to ? "nav-link active" : "nav-link"}
              to=${item.to}
            >
              ${item.label}
            </${Link}>
          `
        )}
      </nav>
      <div className="header-actions">
        ${user?.profile?.avatar_url
          ? html`<${Avatar} src=${user.profile.avatar_url} name="Your profile photo" size="small" />`
          : null}
        ${user?.is_demo ? html`<${Pill} tone="warning">Demo mode</${Pill}>` : null}
        <button className="secondary-button" onClick=${onLogout}>Sign out</button>
      </div>
    </header>
  `;
}

function StatBar({ limits }) {
  if (!limits) return null;
  return html`
    <section className="stat-bar">
      <div>
        <div className="stat-label">Profile views left today</div>
        <div className="stat-value">${limits.profile_views_remaining}</div>
      </div>
      <div>
        <div className="stat-label">Connect requests left today</div>
        <div className="stat-value">${limits.connect_requests_remaining}</div>
      </div>
    </section>
  `;
}

function LandingPage({ onDemoLogin }) {
  return html`
    <main className="landing-shell">
      <section className="landing-copy">
        <${Pill}>MVP</${Pill}>
        <h1>Find serious Cambridge co-founders, then take the conversation off-platform.</h1>
        <p>
          Verified Cambridge students can browse a focused feed, send a short intro request, and unlock LinkedIn or Cambridge email once the other side accepts.
        </p>
        <div className="cta-row">
          <${Link} className="primary-button" to="/login">Sign in with Cambridge email</${Link}>
          <button className="secondary-button" onClick=${onDemoLogin}>Explore demo</button>
        </div>
        <div className="landing-meta">
          <span>Minimal onboarding</span>
          <span>Verified access</span>
          <span>No chat or feed clutter</span>
        </div>
      </section>
      <section className="landing-panel">
        <div className="surface-card">
          <div className="section-heading">How it works</div>
          <div className="stack">
            <div>
              <div className="mini-label">1</div>
              <strong>Verify</strong>
              <p>Cambridge email OTP keeps the network small and trusted.</p>
            </div>
            <div>
              <div className="mini-label">2</div>
              <strong>Scan builders</strong>
              <p>Browse people sorted by commitment and complementary skills.</p>
            </div>
            <div>
              <div className="mini-label">3</div>
              <strong>Unlock contact</strong>
              <p>Contact details stay hidden until a request is accepted.</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  `;
}

function LoginPage({ setAuth }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function requestOtp(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const result = await apiFetch("/auth/request-otp", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (result.delivery_mode === "email") {
        setMessage(`OTP sent to ${result.email}. Check your inbox and enter the 6-digit code.`);
      } else {
        setMessage(`OTP generated for local MVP mode. Use ${result.dev_code} to continue.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function verifyOtp(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await apiFetch("/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({ email, code }),
      });
      saveToken(result.token);
      setAuth({ token: result.token, user: result.user, limits: result.limits });
      navigate(result.user.profile_complete ? "/feed" : "/profile");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return html`
    <main className="page-shell auth-shell">
      <section className="surface-card auth-card">
        <h2>Sign in</h2>
        <p className="muted">Use your Cambridge email. No passwords.</p>
        <form className="form-stack" onSubmit=${requestOtp}>
          <label>
            Cambridge email
            <input
              type="email"
              placeholder="name@cam.ac.uk"
              value=${email}
              onInput=${(event) => setEmail(event.target.value)}
            />
          </label>
          <button className="primary-button" disabled=${loading}>${loading ? "Sending..." : "Send OTP"}</button>
        </form>

        <form className="form-stack verify-form" onSubmit=${verifyOtp}>
          <label>
            OTP code
            <input
              type="text"
              inputMode="numeric"
              placeholder="6-digit code"
              value=${code}
              onInput=${(event) => setCode(event.target.value)}
            />
          </label>
          <button className="primary-button" disabled=${loading}>${loading ? "Verifying..." : "Verify and continue"}</button>
        </form>

        ${message ? html`<div className="success-banner">${message}</div>` : null}
        ${error ? html`<div className="error-banner">${error}</div>` : null}

        <div className="inline-link-row">
          <span>Need a tour first?</span>
          <${Link} to="/">Back to landing page</${Link}>
        </div>
      </section>
    </main>
  `;
}

function ProfileFormPage({ auth, setAuth, api }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    college: "",
    course: "",
    year: 1,
    what_have_you_built: "",
    skills: [],
    commitment_level: "Serious",
    looking_for: "Either",
    linkedin_url: "",
    cam_email: auth.user.email,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const profileComplete = Boolean(auth.user.profile_complete);

  const hydrateFromProfile = React.useCallback(
    (profile) => {
      setForm({
        first_name: profile?.first_name || "",
        last_name: profile?.last_name || "",
        college: profile?.college || "",
        course: profile?.course || "",
        year: profile?.year || 1,
        what_have_you_built: profile?.what_have_you_built || "",
        skills: profile?.skills || [],
        commitment_level: profile?.commitment_level || "Serious",
        looking_for: profile?.looking_for || "Either",
        linkedin_url: profile?.linkedin_url || "",
        cam_email: profile?.cam_email || auth.user.email,
      });
    },
    [auth.user.email]
  );

  useEffect(() => {
    let active = true;
    api("/me")
      .then((result) => {
        if (!active) return;
        setAuth((current) => ({ ...current, user: result.user, limits: result.limits }));
        hydrateFromProfile(result.user.profile);
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [api, hydrateFromProfile, setAuth]);

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function toggleSkill(skill) {
    setForm((current) => {
      const nextSkills = current.skills.includes(skill)
        ? current.skills.filter((value) => value !== skill)
        : [...current.skills, skill].slice(0, 2);
      return { ...current, skills: nextSkills };
    });
  }

  async function saveProfile(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await api("/me/profile", {
        method: "PUT",
        body: JSON.stringify({ ...form, year: Number(form.year) }),
      });
      setAuth((current) => ({
        ...current,
        user: result.user,
      }));
      hydrateFromProfile(result.profile);
      setSuccess("Profile saved.");
      if (!profileComplete) {
        navigate("/feed");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function uploadPhoto(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      formData.append("photo", file);
      const result = await api("/me/profile-photo", {
        method: "POST",
        body: formData,
      });
      setAuth((current) => ({
        ...current,
        user: result.user,
      }));
      setSuccess("Profile photo updated.");
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  if (loading) {
    return html`<main className="page-shell"><div className="surface-card">Loading profile...</div></main>`;
  }

  return html`
    <main className="page-shell">
      <section className="page-intro">
        <${Pill}>Profile</${Pill}>
        <h1>Your builder profile</h1>
        <p>Keep it short. This should take about two minutes.</p>
      </section>
      <section className="surface-card">
        ${auth.user.is_demo ? html`<div className="warning-banner">Demo profiles are seeded and cannot be edited.</div>` : null}

        <div className="photo-panel">
          <${Avatar}
            src=${auth.user.profile?.avatar_url || "/api/avatars/default/0?initials=C"}
            name="Your profile photo"
            size="large"
          />
          <div className="photo-copy">
            <div className="detail-label">Profile photo</div>
            <p className="muted">Everyone gets a default profile image. Upload a JPG, PNG, or WebP to replace it.</p>
            <label className="upload-button">
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange=${uploadPhoto} disabled=${uploading || auth.user.is_demo} />
              ${uploading ? "Uploading..." : "Upload photo"}
            </label>
          </div>
        </div>

        <form className="grid-form" onSubmit=${saveProfile}>
          <label>
            First name
            <input value=${form.first_name} onInput=${(event) => updateField("first_name", event.target.value)} />
          </label>
          <label>
            Last name
            <input value=${form.last_name} onInput=${(event) => updateField("last_name", event.target.value)} />
          </label>
          <label>
            College
            <input value=${form.college} onInput=${(event) => updateField("college", event.target.value)} />
          </label>
          <label>
            Course
            <input value=${form.course} onInput=${(event) => updateField("course", event.target.value)} />
          </label>
          <label>
            Year
            <input
              type="number"
              min="1"
              max="10"
              value=${form.year}
              onInput=${(event) => updateField("year", event.target.value)}
            />
          </label>
          <label>
            Looking for
            <select value=${form.looking_for} onChange=${(event) => updateField("looking_for", event.target.value)}>
              ${LOOKING_FOR_OPTIONS.map((option) => html`<option value=${option}>${option}</option>`)}
            </select>
          </label>
          <label className="full-span">
            What have you built
            <textarea
              rows="4"
              maxLength="300"
              placeholder="A couple of lines on what you have shipped, tested, or run."
              value=${form.what_have_you_built}
              onInput=${(event) => updateField("what_have_you_built", event.target.value)}
            ></textarea>
          </label>
          <div className="full-span">
            <div className="field-label">Skills</div>
            <div className="chip-row">
              ${SKILLS.map(
                (skill) => html`
                  <button
                    type="button"
                    className=${form.skills.includes(skill) ? "chip-button active" : "chip-button"}
                    onClick=${() => toggleSkill(skill)}
                  >
                    ${skill}
                  </button>
                `
              )}
            </div>
            <div className="field-help">Choose up to two.</div>
          </div>
          <label>
            Commitment
            <select value=${form.commitment_level} onChange=${(event) => updateField("commitment_level", event.target.value)}>
              ${COMMITMENT_LEVELS.map((option) => html`<option value=${option}>${option}</option>`)}
            </select>
          </label>
          <label>
            LinkedIn URL
            <input
              placeholder="https://www.linkedin.com/in/..."
              value=${form.linkedin_url}
              onInput=${(event) => updateField("linkedin_url", event.target.value)}
            />
          </label>
          <label className="full-span">
            Cambridge email
            <input type="email" value=${form.cam_email} onInput=${(event) => updateField("cam_email", event.target.value)} />
          </label>
          ${error ? html`<div className="error-banner full-span">${error}</div>` : null}
          ${success ? html`<div className="success-banner full-span">${success}</div>` : null}
          <div className="full-span action-row">
            <button className="primary-button" disabled=${saving || auth.user.is_demo}>
              ${saving ? "Saving..." : profileComplete ? "Save changes" : "Save profile"}
            </button>
            ${profileComplete ? html`<${Link} className="secondary-button" to="/feed">Back to feed</${Link}>` : null}
          </div>
        </form>
      </section>
    </main>
  `;
}

function FeedPage({ api, auth, setAuth }) {
  const [items, setItems] = useState([]);
  const [limits, setLimits] = useState(auth.limits);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api("/feed")
      .then((result) => {
        if (!active) return;
        setItems(result.items);
        setLimits(result.limits);
        setAuth((current) => ({ ...current, limits: result.limits }));
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [api, setAuth]);

  if (loading) {
    return html`<main className="page-shell"><div className="surface-card">Loading feed...</div></main>`;
  }

  return html`
    <main className="page-shell">
      <section className="page-intro">
        <${Pill}>Feed</${Pill}>
        <h1>People you can build with</h1>
        <p>Sorted by commitment first, then complementary skills, with a light college boost.</p>
      </section>
      <${StatBar} limits=${limits} />
      ${error ? html`<div className="error-banner">${error}</div>` : null}
      <section className="feed-grid">
        ${items.map(
          (item) => html`
            <article className="profile-card" key=${item.user_id}>
              <div className="profile-card-top">
                <div className="card-identity">
                  <${Avatar} src=${item.avatar_url} name=${item.name} />
                  <div>
                    <h3>${item.name}</h3>
                    <p>${item.college}</p>
                  </div>
                </div>
                ${item.is_demo_profile ? html`<${Pill} tone="warning">Demo</${Pill}>` : html`<${Pill}>${item.commitment_level}</${Pill}>`}
              </div>
              <div className="meta-line">${item.course} / Year ${item.year}</div>
              <p className="build-text">${item.what_have_you_built}</p>
              <div className="chip-row tight">
                ${item.skills.map((skill) => html`<${Pill}>${skill}</${Pill}>`)}
              </div>
              <div className="match-box">
                ${item.match_reasons.map((reason) => html`<span>${reason}</span>`)}
              </div>
              <${Link} className="text-link" to=${`/profiles/${item.user_id}`}>View profile</${Link}>
            </article>
          `
        )}
      </section>
    </main>
  `;
}

function ProfileDetailPage({ api, auth, setAuth }) {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [limits, setLimits] = useState(auth.limits);
  const [message, setMessage] = useState("Working on a workflow product, want to chat.");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    let active = true;
    api(`/profiles/${userId}`)
      .then((result) => {
        if (!active) return;
        setProfile(result.profile);
        setLimits(result.limits);
        setAuth((current) => ({ ...current, limits: result.limits }));
      })
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, [api, userId, setAuth]);

  async function sendRequest(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const result = await api("/requests", {
        method: "POST",
        body: JSON.stringify({ recipient_user_id: Number(userId), message }),
      });
      setLimits(result.limits);
      setAuth((current) => ({ ...current, limits: result.limits }));
      setSuccess("Connect request sent.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!profile) {
    return html`<main className="page-shell"><div className="surface-card">${error || "Loading profile..."}</div></main>`;
  }

  const isOwnProfile = Number(userId) === auth.user.id;

  return html`
    <main className="page-shell narrow">
      <${StatBar} limits=${limits} />
      <section className="surface-card">
        <div className="page-intro compact profile-header">
          <${Avatar} src=${profile.avatar_url} name=${profile.full_name} size="large" />
          <div>
            <${Pill}>Profile</${Pill}>
            <h1>${profile.full_name}</h1>
            <p>${profile.college} / ${profile.course} / Year ${profile.year}</p>
          </div>
        </div>
        <div className="detail-grid">
          <div>
            <div className="detail-label">What they have built</div>
            <p>${profile.what_have_you_built}</p>
          </div>
          <div>
            <div className="detail-label">Skills</div>
            <div className="chip-row tight">
              ${profile.skills.map((skill) => html`<${Pill}>${skill}</${Pill}>`)}
            </div>
          </div>
          <div>
            <div className="detail-label">Commitment</div>
            <p>${profile.commitment_level}</p>
          </div>
          <div>
            <div className="detail-label">Looking for</div>
            <p>${profile.looking_for}</p>
          </div>
          <div className="full-span">
            <div className="detail-label">Why this match is near the top</div>
            <div className="match-box">
              ${profile.match_reasons.map((reason) => html`<span>${reason}</span>`)}
            </div>
          </div>
          <div className="full-span">
            <div className="detail-label">Contact</div>
            ${profile.contact_unlocked
              ? html`
                  <div className="contact-box">
                    <a href=${profile.linkedin_url} target="_blank" rel="noreferrer">LinkedIn</a>
                    <a href=${`mailto:${profile.cam_email}`}>${profile.cam_email}</a>
                  </div>
                `
              : html`<div className="locked-contact">Hidden until a connect request is accepted.</div>`}
          </div>
        </div>
      </section>

      ${isOwnProfile
        ? html`
            <div className="action-row">
              <button className="secondary-button" onClick=${() => navigate("/profile")}>Edit profile</button>
            </div>
          `
        : html`
            <section className="surface-card">
              ${auth.user.is_demo
                ? html`<div className="warning-banner">Demo users can browse the feed but cannot send requests or unlock real contact details.</div>`
                : html`
                    <form className="form-stack" onSubmit=${sendRequest}>
                      <label>
                        Short intro message
                        <textarea
                          rows="3"
                          placeholder="Working on X, want to chat"
                          value=${message}
                          onInput=${(event) => setMessage(event.target.value)}
                        ></textarea>
                      </label>
                      ${error ? html`<div className="error-banner">${error}</div>` : null}
                      ${success ? html`<div className="success-banner">${success}</div>` : null}
                      <div className="action-row">
                        <button className="primary-button" disabled=${submitting}>
                          ${submitting ? "Sending..." : "Connect"}
                        </button>
                      </div>
                    </form>
                  `}
            </section>
          `}
    </main>
  `;
}

function RequestsPage({ api }) {
  const [data, setData] = useState({ incoming: [], outgoing: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const result = await api("/requests");
      setData(result.requests);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function respond(id, status) {
    setError("");
    try {
      await api(`/requests/${id}/respond`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) {
    return html`<main className="page-shell"><div className="surface-card">Loading requests...</div></main>`;
  }

  return html`
    <main className="page-shell">
      <section className="page-intro">
        <${Pill}>Requests</${Pill}>
        <h1>Connect requests</h1>
        <p>Accept to unlock contact details. Decline to keep things tidy.</p>
      </section>
      ${error ? html`<div className="error-banner">${error}</div>` : null}
      <section className="split-grid">
        <div className="surface-card">
          <div className="section-heading">Incoming</div>
          <div className="stack">
            ${data.incoming.length === 0
              ? html`<div className="empty-state">No incoming requests.</div>`
              : data.incoming.map(
                  (request) => html`
                    <article className="request-item" key=${request.id}>
                      <div className="request-head">
                        <div className="card-identity">
                          <${Avatar} src=${request.counterparty.avatar_url} name=${request.counterparty.first_name} />
                          <div>
                            <strong>${request.counterparty.first_name} ${request.counterparty.last_name}</strong>
                            <div className="muted">${request.counterparty.college} / ${request.counterparty.course}</div>
                          </div>
                        </div>
                      </div>
                      <p>${request.message}</p>
                      <div className="request-footer">
                        <${Pill}>${request.status}</${Pill}>
                        ${request.status === "pending"
                          ? html`
                              <div className="action-row">
                                <button className="secondary-button" onClick=${() => respond(request.id, "declined")}>Decline</button>
                                <button className="primary-button" onClick=${() => respond(request.id, "accepted")}>Accept</button>
                              </div>
                            `
                          : null}
                      </div>
                    </article>
                  `
                )}
          </div>
        </div>
        <div className="surface-card">
          <div className="section-heading">Outgoing</div>
          <div className="stack">
            ${data.outgoing.length === 0
              ? html`<div className="empty-state">No outgoing requests.</div>`
              : data.outgoing.map(
                  (request) => html`
                    <article className="request-item" key=${request.id}>
                      <div className="card-identity">
                        <${Avatar} src=${request.counterparty.avatar_url} name=${request.counterparty.first_name} />
                        <div>
                          <strong>${request.counterparty.first_name} ${request.counterparty.last_name}</strong>
                          <div className="muted">${request.counterparty.college} / ${request.counterparty.course}</div>
                        </div>
                      </div>
                      <p>${request.message}</p>
                      <div className="request-footer">
                        <${Pill}>${request.status}</${Pill}>
                      </div>
                    </article>
                  `
                )}
          </div>
        </div>
      </section>
    </main>
  `;
}

function ConnectionsPage({ api, auth }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api("/connections")
      .then((result) => {
        if (!active) return;
        setItems(result.items);
      })
      .catch((err) => active && setError(err.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [api]);

  if (loading) {
    return html`<main className="page-shell"><div className="surface-card">Loading connections...</div></main>`;
  }

  return html`
    <main className="page-shell">
      <section className="page-intro">
        <${Pill}>Connections</${Pill}>
        <h1>Accepted connections</h1>
        <p>Once a request is accepted, LinkedIn and Cambridge email appear here.</p>
      </section>
      ${auth.user.is_demo ? html`<div className="warning-banner">Demo mode keeps contact details hidden even for accepted sample connections.</div>` : null}
      ${error ? html`<div className="error-banner">${error}</div>` : null}
      <section className="feed-grid">
        ${items.length === 0
          ? html`<div className="surface-card empty-state">No accepted connections yet.</div>`
          : items.map(
              (item) => html`
                <article className="profile-card" key=${item.request_id}>
                  <div className="profile-card-top">
                    <div className="card-identity">
                      <${Avatar} src=${item.counterparty.avatar_url} name=${item.counterparty.first_name} />
                      <div>
                        <h3>${item.counterparty.first_name} ${item.counterparty.last_name}</h3>
                        <p>${item.counterparty.college}</p>
                      </div>
                    </div>
                    <${Pill}>${item.counterparty.commitment_level}</${Pill}>
                  </div>
                  <div className="meta-line">${item.counterparty.course} / Year ${item.counterparty.year}</div>
                  <div className="chip-row tight">
                    ${item.counterparty.skills.map((skill) => html`<${Pill}>${skill}</${Pill}>`)}
                  </div>
                  <div className="contact-box">
                    ${item.counterparty.linkedin_url
                      ? html`<a href=${item.counterparty.linkedin_url} target="_blank" rel="noreferrer">LinkedIn</a>`
                      : html`<span className="locked-contact small">LinkedIn hidden in demo mode</span>`}
                    ${item.counterparty.cam_email
                      ? html`<a href=${`mailto:${item.counterparty.cam_email}`}>${item.counterparty.cam_email}</a>`
                      : html`<span className="locked-contact small">Email hidden in demo mode</span>`}
                  </div>
                </article>
              `
            )}
      </section>
    </main>
  `;
}

function ProtectedRoute({ auth, children }) {
  if (!auth?.token) {
    return html`<${Navigate} to="/" replace=${true} />`;
  }
  return children;
}

function AuthenticatedApp({ auth, setAuth }) {
  const navigate = useNavigate();
  const handleUnauthorized = React.useCallback(() => {
    saveToken("");
    setAuth(null);
    navigate("/");
  }, [navigate, setAuth]);
  const api = React.useMemo(() => createApiClient(auth.token, handleUnauthorized), [auth.token, handleUnauthorized]);
  const safeSetAuth = React.useCallback(
    (updater) => {
      setAuth((current) => (typeof updater === "function" ? updater(current) : updater));
    },
    [setAuth]
  );

  async function handleLogout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch (_) {
      // Ignore logout errors and clear local state anyway.
    }
    saveToken("");
    setAuth(null);
    navigate("/");
  }

  return html`
    <div className="app-shell">
      <${Header} user=${auth.user} onLogout=${handleLogout} />
      <${Routes}>
        <${Route}
          path="/profile"
          element=${html`<${ProfileFormPage} auth=${auth} setAuth=${safeSetAuth} api=${api} />`}
        />
        <${Route} path="/feed" element=${html`<${FeedPage} auth=${auth} setAuth=${safeSetAuth} api=${api} />`} />
        <${Route}
          path="/profiles/:userId"
          element=${html`<${ProfileDetailPage} auth=${auth} setAuth=${safeSetAuth} api=${api} />`}
        />
        <${Route} path="/requests" element=${html`<${RequestsPage} api=${api} />`} />
        <${Route} path="/connections" element=${html`<${ConnectionsPage} api=${api} auth=${auth} />`} />
        <${Route}
          path="*"
          element=${html`<${Navigate} to=${auth.user.profile_complete ? "/feed" : "/profile"} replace=${true} />`}
        />
      </${Routes}>
    </div>
  `;
}

function RootApp() {
  const navigate = useNavigate();
  const [auth, setAuth] = useState(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    const token = loadToken();
    if (!token) {
      setBooting(false);
      return;
    }
    apiFetch("/me", {}, token)
      .then((result) => setAuth({ token, user: result.user, limits: result.limits }))
      .catch(() => saveToken(""))
      .finally(() => setBooting(false));
  }, []);

  async function handleDemoLogin() {
    const result = await apiFetch("/auth/demo-login", { method: "POST" });
    saveToken(result.token);
    setAuth({ token: result.token, user: result.user, limits: result.limits });
    navigate("/feed");
  }

  if (booting) {
    return html`<main className="page-shell"><div className="surface-card">Loading...</div></main>`;
  }

  return html`
    <${Routes}>
      <${Route}
        path="/"
        element=${auth ? html`<${Navigate} to=${auth.user.profile_complete ? "/feed" : "/profile"} replace=${true} />` : html`<${LandingPage} onDemoLogin=${handleDemoLogin} />`}
      />
      <${Route}
        path="/login"
        element=${auth ? html`<${Navigate} to=${auth.user.profile_complete ? "/feed" : "/profile"} replace=${true} />` : html`<${LoginPage} setAuth=${setAuth} />`}
      />
      <${Route}
        path="/*"
        element=${html`<${ProtectedRoute} auth=${auth}><${AuthenticatedApp} auth=${auth} setAuth=${setAuth} /></${ProtectedRoute}>`}
      />
    </${Routes}>
  `;
}

function App() {
  return html`<${HashRouter}><${RootApp} /></${HashRouter}>`;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
