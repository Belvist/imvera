import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            HistoryView()
                .tabItem { Label("История", systemImage: "clock") }
            AlertsView()
                .tabItem { Label("Тревоги", systemImage: "exclamationmark.triangle") }
            FamilyView()
                .tabItem { Label("Семья", systemImage: "person.3") }
            ScheduleView()
                .tabItem { Label("Расписание", systemImage: "calendar") }
        }
    }
}

struct HistoryView: View {
    var body: some View {
        NavigationStack {
            List {
                Text("Статусы появятся после подключения Product API")
                    .foregroundStyle(.secondary)
            }
            .navigationTitle("История")
        }
    }
}

struct AlertsView: View {
    var body: some View {
        NavigationStack {
            List {
                Text("Нет открытых тревог")
                    .foregroundStyle(.secondary)
                Button("Я проверю") {}
                    .disabled(true)
            }
            .navigationTitle("Тревоги")
        }
    }
}

struct FamilyView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("Подопечные") {
                    Text("Добавьте профиль родственника")
                }
                Section("Контакты эскалации") {
                    Text("Порядок: push → Telegram → SMS → звонок")
                }
            }
            .navigationTitle("Семья")
        }
    }
}

struct ScheduleView: View {
    var body: some View {
        NavigationStack {
            Form {
                Toggle("Расписание включено", isOn: .constant(false))
                Text("Окна и quiet hours — после Product API /schedules")
                Button("Позвонить сейчас") {}
                    .disabled(true)
            }
            .navigationTitle("Расписание")
        }
    }
}

#Preview {
    RootTabView()
}
