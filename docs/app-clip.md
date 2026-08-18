# App Clip spec — QR join with no download

Goal: a guest points the iPhone camera at a printed QR on a wedding table, taps the
banner, and is shooting within seconds — no App Store download. Android and desktop
guests hit the same URL and get the web PWA instead.

This is how Once delivers "no download needed for guests."

---

## Hard prerequisites

1. **A full iOS app must be published on the App Store.** An App Clip is a target
   attached to a full app; it cannot be distributed alone. This is why App Clip work
   sits in Phase 5 and not Phase 1.
2. **A verified domain** you control (`filmroll.app`) serving an
   `apple-app-site-association` file over HTTPS.
3. **An Advanced App Clip Experience** configured in App Store Connect — required for
   invocation from QR codes, NFC tags, and App Clip Codes.

---

## Size budget

The uncompressed App Clip binary limit depends on how it is invoked:

| Minimum deployment target | Limit | Notes |
|---|---|---|
| iOS 15 and earlier | 10 MB | |
| iOS 16 and later | **15 MB** | **This is our bucket** |
| iOS 17 and later | 100 MB | Only if the clip supports *digital* invocation only — no QR, NFC, or App Clip Codes |

Because our whole point is a printed QR (a physical invocation), we are capped at
**15 MB uncompressed after app thinning**. Budget accordingly:

- SwiftUI + AVFoundation capture only
- No analytics SDKs, no image-processing frameworks, no Lottie, no fonts beyond system
- Filters in the clip = a small Core Image chain or none at all
- Share the networking/model code with the full app via a local Swift package, but
  keep clip-only targets lean

Verify size in Xcode's build report before every submission. It fails at App Store
Connect upload, not at compile time.

---

## URL design

Keep the invocation URL short. App Clip Codes compress the URL into a **128-bit**
payload, so long URLs are rejected outright.

```
Invocation URL:   https://filmroll.app/f/6GQ63P
                  └─ prefix ───────┘ └ code ┘
```

Our existing 6-character film code (`6GQ63P`) already fits comfortably. Do not add
query parameters to the printed URL — put state on the server keyed by the code.

One Advanced App Clip Experience with the URL prefix `https://filmroll.app/f/` covers
every film. You do **not** register an experience per event.

---

## Server configuration

Serve this at `https://filmroll.app/.well-known/apple-app-site-association` with
`Content-Type: application/json`, no redirects, no `.json` extension.

```json
{
  "appclips": {
    "apps": ["TEAMID.app.filmroll.Clip"]
  },
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID.app.filmroll"],
        "components": [{ "/": "/f/*" }]
      }
    ]
  }
}
```

In the App Clip target's entitlements:

```
com.apple.developer.associated-domains = ["appclips:filmroll.app"]
```

In `Info.plist` for the clip, add usage strings or review will reject the build:

```
NSCameraUsageDescription — "Used to take photos for the event you joined."
```

---

## Launch handling

The clip receives the URL through a user activity, not a custom scheme (custom URL
schemes are unavailable to App Clips).

```swift
@main
struct FilmrollClipApp: App {
    @State private var filmCode: String?

    var body: some Scene {
        WindowGroup {
            ClipRootView(filmCode: filmCode)
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    guard
                        let url = activity.webpageURL,
                        let code = Self.code(from: url)
                    else { return }
                    filmCode = code
                }
        }
    }

    // https://filmroll.app/f/6GQ63P -> "6GQ63P"
    private static func code(from url: URL) -> String? {
        let parts = url.pathComponents.filter { $0 != "/" }
        guard parts.first == "f", parts.count >= 2 else { return nil }
        return parts[1]
    }
}
```

Flow inside the clip: parse code → `GET /api/films/{code}` → name prompt →
`POST /api/films/{code}/join` → camera → `POST /api/films/{code}/shots`.

---

## What the clip must not try to do

These are platform restrictions, confirmed against Apple's documentation. Designing
around them is not optional.

| Restriction | Workaround in Filmroll |
|---|---|
| No Photos library access (PhotoKit is inert) | No camera-roll upload in the clip. To save a photo, present a share sheet (`UIActivityViewController`) and let the user choose. |
| No background activity or background `URLSession` | Upload must complete while the clip is in the foreground. Show explicit progress and warn before dismissal if the queue is non-empty. |
| No in-app purchase | Hosts never buy from the clip. Purchases live in the full app (StoreKit 2) or on the web (Stripe). |
| Ephemeral storage, stops after ~8h idle | Guest identity lives server-side, keyed by a token. Do not rely on local persistence between sessions. |
| Notifications are ephemeral (8h or 24h) | Good enough for "your film develops tomorrow morning," not for long-tail re-engagement. Use email for that. |
| Location is when-in-use only | Geo-locking a venue is possible; background geofencing is not. |
| No custom URL schemes, no App Intents | All entry is via the universal link above. |

---

## Handoff to the full app

Offer the full app at a natural moment — after the guest's roll is empty, not on
launch.

- Present `SKOverlay.AppClipConfiguration` to promote the full app
- Share state through an **App Group** so a guest who installs the full app keeps
  their identity and shot count
- The full app is where they browse the developed gallery, save originals, and
  create their own film

---

## Fallback matrix

The same printed QR must work for everyone. The web route `/f/[code]` already
handles the non-iOS cases.

| Guest device | What happens |
|---|---|
| iPhone, iOS 16+, clip configured | App Clip card appears, opens native camera |
| iPhone, declined the clip | Safari opens `/f/[code]` PWA camera |
| iPhone, full app installed | Universal link opens the full app directly |
| Android | Chrome opens `/f/[code]` PWA camera |
| Desktop | Web page with the film info and a "scan on your phone" prompt |

**Rule: the web experience must be complete on its own.** The App Clip is an
upgrade for iPhone guests, never a requirement.

---

## Testing before the domain is live

`appclip.apple.com` **default App Clip links** work from iOS 16.4 without any AASA
setup, and App Store Connect generates a **demo link** — useful for testing the clip
before DNS and associated domains are configured.

Caveats: the default link cannot be used inside an App Clip Code, and the demo link
cannot carry launch parameters. Do not print either one on wedding cards; use them
for development only.

Local testing: set the `_XCAppClipURL` environment variable in the Xcode scheme to
simulate an invocation URL.

---

## Submission checklist

- [ ] Full iOS app approved and live on the App Store
- [ ] Clip binary verified under 15 MB uncompressed after thinning
- [ ] AASA served at `/.well-known/apple-app-site-association`, 200, no redirect
- [ ] `appclips:filmroll.app` in the clip's associated-domains entitlement
- [ ] Advanced App Clip Experience created with prefix `https://filmroll.app/f/`
- [ ] Card image, title, subtitle, and action verb set for the experience
- [ ] `NSCameraUsageDescription` written in plain language
- [ ] Tested: printed QR → clip → join → shoot → upload completes in foreground
- [ ] Tested: same QR on Android falls back to the PWA
