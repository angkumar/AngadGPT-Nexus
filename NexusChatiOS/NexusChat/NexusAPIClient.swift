import Foundation

struct NexusAPIClient {
    var baseURL: URL
    var token: String

    func health() async throws {
        let url = baseURL.appending(path: "health")
        let (_, response) = try await URLSession.shared.data(for: URLRequest(url: url))
        try validate(response: response, data: Data())
    }

    func send(message: String) async throws -> String {
        let url = baseURL.appending(path: "agent/step")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder().encode(AgentStepRequest(message: message))

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
        return normalizeAssistantContent(from: data)
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw NexusAPIError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "No response body"
            throw NexusAPIError.http(statusCode: httpResponse.statusCode, body: body)
        }
    }

    private func normalizeAssistantContent(from data: Data) -> String {
        if let response = try? JSONDecoder().decode(AgentStepResponse.self, from: data) {
            if let content = response.content {
                return normalize(rawContent: content)
            }
            if response.action == "respond", let content = response.content {
                return content
            }
        }

        if let object = try? JSONSerialization.jsonObject(with: data),
           let pretty = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted]),
           let text = String(data: pretty, encoding: .utf8) {
            return text
        }

        return String(data: data, encoding: .utf8) ?? ""
    }

    private func normalize(rawContent: String) -> String {
        let trimmed = rawContent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.first == "{",
              trimmed.contains("\"action\""),
              trimmed.contains("\"content\""),
              let data = trimmed.data(using: .utf8),
              let wrapped = try? JSONDecoder().decode(WrappedAssistantResponse.self, from: data),
              wrapped.action == "respond",
              let content = wrapped.content else {
            return rawContent
        }
        return content
    }
}

enum NexusAPIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case http(statusCode: Int, body: String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            "The API URL is not valid."
        case .invalidResponse:
            "Nexus returned an invalid response."
        case let .http(statusCode, body):
            "API error \(statusCode): \(body)"
        }
    }
}
