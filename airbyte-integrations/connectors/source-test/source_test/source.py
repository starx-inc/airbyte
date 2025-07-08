from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream


class UsersStream(HttpStream):
    url_base = "https://jsonplaceholder.typicode.com/"
    primary_key = "id"

    def path(self, **kwargs) -> str:
        return "users"

    def parse_response(self, response: requests.Response, **kwargs) -> Iterable[Mapping]:
        return response.json()

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        return None

    def get_json_schema(self) -> Mapping[str, Any]:
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "username": {"type": "string"},
                "email": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "suite": {"type": "string"},
                        "city": {"type": "string"},
                        "zipcode": {"type": "string"},
                        "geo": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "string"},
                                "lng": {"type": "string"}
                            }
                        }
                    }
                },
                "phone": {"type": "string"},
                "website": {"type": "string"},
                "company": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "catchPhrase": {"type": "string"},
                        "bs": {"type": "string"}
                    }
                }
            }
        }


class SourceTest(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            stream = UsersStream(authenticator=None)
            records = stream.read_records(sync_mode="full_refresh")
            next(records)
            return True, None
        except Exception as e:
            return False, f"Unable to connect to JSONPlaceholder API: {str(e)}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        return [UsersStream(authenticator=None)]