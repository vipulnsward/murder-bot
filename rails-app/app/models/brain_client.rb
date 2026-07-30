require "net/http"

class BrainClient
  DEFAULT_URL = "https://178-156-152-222.sslip.io"

  class << self
    def url
      ENV.fetch("BRAIN_URL", DEFAULT_URL)
    end

    def counter_generals(query)
      uri = endpoint("/api/counter-generals")
      uri.query = query.presence
      response = request(uri, Net::HTTP::Get, timeout: 5)
      response.body if response.is_a?(Net::HTTPSuccess)
    rescue StandardError
      nil
    end

    def reachable?
      request(endpoint("/"), Net::HTTP::Head, timeout: 2)
      true
    rescue StandardError
      false
    end

    private

    def endpoint(path)
      URI("#{url.chomp("/")}#{path}")
    end

    def request(uri, request_class, timeout:)
      Net::HTTP.start(
        uri.host,
        uri.port,
        use_ssl: uri.scheme == "https",
        open_timeout: timeout,
        read_timeout: timeout
      ) { |http| http.request(request_class.new(uri)) }
    end
  end
end
