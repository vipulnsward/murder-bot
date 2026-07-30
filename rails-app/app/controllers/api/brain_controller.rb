module Api
  class BrainController < ApplicationController
    def counter_generals
      body = BrainClient.counter_generals(request.query_string)

      if body
        render body:, content_type: "application/json"
      else
        render json: { enemy: params[:enemy], recommendations: [], error: "brain unavailable" }
      end
    end
  end
end
