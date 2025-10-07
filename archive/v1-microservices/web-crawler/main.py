import os
from datetime import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
import structlog
import asyncio
import httpx
from bs4 import BeautifulSoup
import redis.asyncio as redis

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger(__name__)

app = FastAPI(title="Web Crawler Service", description="Web content crawling and extraction service", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Global services
redis_client: redis.Redis = None

class CrawlRequest(BaseModel):
    url: HttpUrl
    max_depth: int = 1
    follow_links: bool = False
    extract_text_only: bool = True

class CrawlResponse(BaseModel):
    success: bool
    url: str
    title: str = ""
    content: str = ""
    links: List[str] = []
    timestamp: str

@app.on_event("startup")
async def startup_event():
    global redis_client

    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()

        logger.info("Web Crawler Service started successfully")

    except Exception as e:
        logger.error("Failed to initialize Web Crawler service", error=str(e))
        raise

@app.on_event("shutdown")
async def shutdown_event():
    if redis_client:
        await redis_client.close()

async def extract_content_from_html(html: str, extract_text_only: bool = True) -> Dict[str, Any]:
    """Extract content from HTML"""
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        if extract_text_only:
            # Extract text content
            text = soup.get_text()
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            content = ' '.join(chunk for chunk in chunks if chunk)
        else:
            # Keep HTML structure but clean it
            content = str(soup)

        # Extract links
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                links.append(href)

        return {
            "title": title,
            "content": content,
            "links": links
        }

    except Exception as e:
        logger.error("Error extracting content from HTML", error=str(e))
        return {"title": "", "content": "", "links": []}

async def crawl_url(url: str, extract_text_only: bool = True) -> Dict[str, Any]:
    """Crawl a single URL"""
    try:
        # Check cache first
        cache_key = f"crawl:{url}"
        cached_result = await redis_client.get(cache_key)

        if cached_result:
            import json
            logger.info("Returning cached crawl result", url=url)
            return json.loads(cached_result)

        # Make HTTP request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Extract content
            extracted = await extract_content_from_html(response.text, extract_text_only)

            result = {
                "success": True,
                "url": url,
                "title": extracted["title"],
                "content": extracted["content"],
                "links": extracted["links"],
                "timestamp": datetime.utcnow().isoformat()
            }

            # Cache result for 1 hour
            import json
            await redis_client.setex(cache_key, 3600, json.dumps(result))

            logger.info("Successfully crawled URL", url=url, content_length=len(extracted["content"]))
            return result

    except httpx.HTTPStatusError as e:
        logger.error("HTTP error crawling URL", url=url, status_code=e.response.status_code)
        return {
            "success": False,
            "url": url,
            "error": f"HTTP {e.response.status_code}",
            "timestamp": datetime.utcnow().isoformat()
        }
    except httpx.RequestError as e:
        logger.error("Request error crawling URL", url=url, error=str(e))
        return {
            "success": False,
            "url": url,
            "error": f"Request error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Unexpected error crawling URL", url=url, error=str(e))
        return {
            "success": False,
            "url": url,
            "error": f"Unexpected error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await redis_client.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "redis_status": redis_status
    }

@app.post("/crawl", response_model=CrawlResponse)
async def crawl_single_url(request: CrawlRequest):
    """Crawl a single URL"""
    try:
        result = await crawl_url(str(request.url), request.extract_text_only)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Crawl failed"))

        return CrawlResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in crawl endpoint", error=str(e))
        raise HTTPException(status_code=500, detail=f"Crawl failed: {str(e)}")

@app.post("/crawl/batch")
async def crawl_multiple_urls(urls: List[HttpUrl], extract_text_only: bool = True):
    """Crawl multiple URLs concurrently"""
    try:
        # Limit to 10 URLs to prevent abuse
        if len(urls) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 URLs allowed per batch")

        # Create tasks for concurrent crawling
        tasks = [crawl_url(str(url), extract_text_only) for url in urls]

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "url": str(urls[i]),
                    "error": str(result),
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                processed_results.append(result)

        successful_crawls = sum(1 for r in processed_results if r.get("success", False))

        return {
            "success": True,
            "total_urls": len(urls),
            "successful_crawls": successful_crawls,
            "results": processed_results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in batch crawl endpoint", error=str(e))
        raise HTTPException(status_code=500, detail=f"Batch crawl failed: {str(e)}")

@app.get("/cache/stats")
async def get_cache_stats():
    """Get crawl cache statistics"""
    try:
        keys = await redis_client.keys("crawl:*")
        cache_size = len(keys)

        # Get sample of recent crawls
        recent_crawls = []
        for key in keys[:5]:  # Show last 5
            url = key.replace("crawl:", "")
            ttl = await redis_client.ttl(key)
            recent_crawls.append({
                "url": url,
                "ttl_seconds": ttl
            })

        return {
            "cache_size": cache_size,
            "recent_crawls": recent_crawls
        }

    except Exception as e:
        logger.error("Error getting cache stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get cache stats")

@app.delete("/cache/clear")
async def clear_cache():
    """Clear crawl cache"""
    try:
        keys = await redis_client.keys("crawl:*")
        if keys:
            deleted = await redis_client.delete(*keys)
            return {"success": True, "deleted_entries": deleted}
        else:
            return {"success": True, "deleted_entries": 0}

    except Exception as e:
        logger.error("Error clearing cache", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)