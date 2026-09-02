import Foundation

enum FamilyStatus: String, Codable, CaseIterable {
    case green = "GREEN"
    case yellow = "YELLOW"
    case red = "RED"
    case noContact = "NO_CONTACT"
    case technical = "TECHNICAL"
    case declined = "DECLINED"

    var titleRU: String {
        switch self {
        case .green: return "Всё в порядке"
        case .yellow: return "Нужно внимание"
        case .red: return "Тревога"
        case .noContact: return "Не удалось связаться"
        case .technical: return "Техническая ошибка"
        case .declined: return "Отказ от звонков"
        }
    }
}

struct CallHistoryItem: Codable, Identifiable {
    var id: String
    var startedAt: Date
    var familyStatus: FamilyStatus
    var summaryForFamily: String
    var durationSec: Int?
}

struct IncidentItem: Codable, Identifiable {
    var id: String
    var status: String
    var severity: String
    var openedAt: Date
    var reason: String?
}
