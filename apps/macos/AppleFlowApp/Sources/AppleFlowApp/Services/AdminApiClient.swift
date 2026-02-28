import Foundation

protocol AdminApiClientProtocol {
    func health() async throws -> Bool
    func metrics() async throws -> MetricsResponse
    func sessions() async throws -> [SessionItem]
    func approvals() async throws -> [ApprovalItem]
    func overrideApproval(requestID: String, status: String) async throws -> ApprovalOverrideResponse
    func events(limit: Int) async throws -> [AuditEvent]
}

final class AdminApiClient: AdminApiClientProtocol {
    private let credentials: AdminCredentials
    private let decoder: JSONDecoder

    init(credentials: AdminCredentials) {
        self.credentials = credentials
        self.decoder = JSONDecoder()
        self.decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    func health() async throws -> Bool {
        let payload: [String: String] = try await request(path: "/health", method: "GET")
        return payload["status"] == "ok"
    }

    func metrics() async throws -> MetricsResponse {
        try await request(path: "/metrics", method: "GET")
    }

    func sessions() async throws -> [SessionItem] {
        try await request(path: "/sessions", method: "GET")
    }

    func approvals() async throws -> [ApprovalItem] {
        try await request(path: "/approvals/pending", method: "GET")
    }

    func overrideApproval(requestID: String, status: String) async throws -> ApprovalOverrideResponse {
        let body = ["status": status]
        return try await request(path: "/approvals/\(requestID)/override", method: "POST", body: body)
    }

    func events(limit: Int) async throws -> [AuditEvent] {
        try await request(path: "/audit/events?limit=\(limit)", method: "GET")
    }

    private func request<T: Decodable>(
        path: String,
        method: String
    ) async throws -> T {
        try await executeRequest(path: path, method: method, encodedBody: nil)
    }

    private func request<T: Decodable, B: Encodable>(
        path: String,
        method: String,
        body: B
    ) async throws -> T {
        let encodedBody = try JSONEncoder().encode(body)
        return try await executeRequest(path: path, method: method, encodedBody: encodedBody)
    }

    private func executeRequest<T: Decodable>(
        path: String,
        method: String,
        encodedBody: Data?
    ) async throws -> T {
        let base = "http://\(credentials.host):\(credentials.port)"
        guard let url = URL(string: base + path) else {
            throw AppViewError.networkFailed("Invalid API URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if !credentials.token.isEmpty {
            request.setValue("Bearer \(credentials.token)", forHTTPHeaderField: "Authorization")
        }

        if let encodedBody {
            request.httpBody = encodedBody
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AppViewError.networkFailed("No HTTP response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let raw = String(data: data, encoding: .utf8) ?? "<no body>"
            throw AppViewError.networkFailed("API \(httpResponse.statusCode): \(raw)")
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            let raw = String(data: data, encoding: .utf8) ?? "<invalid utf8>"
            throw AppViewError.decodeFailed("Failed to decode API response: \(raw)")
        }
    }
}
