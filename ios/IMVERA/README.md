# IMVERA Family App (iOS 17+)

SwiftUI scaffold for ROADMAP E8. Product API base URL:
`MOSS_PRODUCT_URL` / Info.plist `ProductAPIBaseURL` (default `https://api.imvera.ru`).

## Tabs (match imvera.ru mock)

1. **История** — call list with family_status + summary
2. **Тревоги** — incidents + «Я проверю» (ack)
3. **Семья** — elders, contacts, roles, invite
4. **Расписание** — windows, quiet hours, pause, call now

## Build

Open `ios/IMVERA` in Xcode 16+, set Team + bundle `ru.imvera.app`,
enable Push Notifications + Time Sensitive Notifications entitlement,
configure APNs key for backend E6.

## Disclaimer (App Store)

IMVERA is a family communication service, not a medical device and not
emergency services. In life-threatening situations call 112.
