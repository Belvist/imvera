import Foundation

actor ProductAPIClient {
    var baseURL: URL
    var accessToken: String?

    init(baseURL: URL = URL(string: "http://127.0.0.1:9480")!) {
        self.baseURL = baseURL
    }

    func requestOTP(phone: String) async throws {
        try await post(path: "/api/v1/auth/otp/request", body: ["phone": phone])
    }

    func verifyOTP(phone: String, code: String) async throws -> String {
        let data = try await postData(
            path: "/api/v1/auth/otp/verify",
            body: ["phone": phone, "code": code])
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let token = obj?["access_token"] as? String else {
            throw URLError(.cannotParseResponse)
        }
        accessToken = token
        return token
    }

    func calls(elderId: String) async throws -> [CallHistoryItem] {
        try await get(path: "/api/v1/elders/\(elderId)/calls")
    }

    func ackIncident(id: String, note: String? = nil) async throws {
        var body: [String: String] = [:]
        if let note { body["note"] = note }
        try await post(path: "/api/v1/incidents/\(id)/ack", body: body)
    }

    private func get<T: Decodable>(path: String) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "GET"
        if let accessToken {
            req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        let dec = JSONDecoder()
        dec.dateDecodingStrategy = .iso8601
        return try dec.decode(T.self, from: data)
    }

    @discardableResult
    private func post(path: String, body: [String: String]) async throws -> Data {
        try await postData(path: path, body: body)
    }

    private func postData(path: String, body: [String: String]) async throws -> Data {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let accessToken {
            req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }
}
