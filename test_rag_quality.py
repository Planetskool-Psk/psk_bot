#!/usr/bin/env python3
"""
RAG Quality Assessment Script
Tests the quality of answers before and after optimization
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gentari_bot.services import RAGService
from utils.logger import log
import time

def test_rag_quality():
    """Test the quality of RAG responses with various query types."""
    
    # Test queries of different types
    test_queries = [
        {
            "query": "What are the company's vacation policies?",
            "type": "Policy Question",
            "expected_keywords": ["vacation", "policy", "days", "time off"]
        },
        {
            "query": "How do I apply for medical leave?",
            "type": "Process Question", 
            "expected_keywords": ["medical", "leave", "apply", "process"]
        },
        {
            "query": "What benefits does the company offer?",
            "type": "Benefits Question",
            "expected_keywords": ["benefits", "insurance", "health", "coverage"]
        },
        {
            "query": "What are the working hours?",
            "type": "Simple Factual",
            "expected_keywords": ["hours", "work", "schedule", "time"]
        },
        {
            "query": "Tell me about performance reviews",
            "type": "General Information",
            "expected_keywords": ["performance", "review", "evaluation", "assessment"]
        }
    ]
    
    log.info("🧪 Starting RAG Quality Assessment...")
    log.info("=" * 60)
    
    rag_service = RAGService()
    
    if not rag_service.ready:
        log.error("❌ RAG service not ready. Please run document ingestion first.")
        return
    
    results = []
    
    for i, test_case in enumerate(test_queries, 1):
        log.info(f"\n📝 Test {i}: {test_case['type']}")
        log.info(f"Question: {test_case['query']}")
        log.info("-" * 40)
        
        start_time = time.time()
        
        # Get response
        response_chunks = []
        try:
            for chunk in rag_service.get_response_stream(test_case['query'], []):
                response_chunks.append(chunk)
            
            response = ''.join(response_chunks)
            response_time = time.time() - start_time
            
            # Assess response quality
            quality_score = assess_response_quality(response, test_case['expected_keywords'])
            
            result = {
                "query": test_case['query'],
                "type": test_case['type'],
                "response": response,
                "response_time": response_time,
                "quality_score": quality_score,
                "response_length": len(response),
                "keyword_matches": count_keyword_matches(response, test_case['expected_keywords'])
            }
            
            results.append(result)
            
            # Display results
            log.info(f"✅ Response received in {response_time:.2f}s")
            log.info(f"📏 Response length: {len(response)} characters")
            log.info(f"🎯 Quality score: {quality_score:.2f}/5.0")
            log.info(f"🔍 Keyword matches: {result['keyword_matches']}/{len(test_case['expected_keywords'])}")
            
            # Show response preview
            preview = response[:200] + "..." if len(response) > 200 else response
            log.info(f"📖 Response preview: {preview}")
            
        except Exception as e:
            log.error(f"❌ Error getting response: {e}")
            result = {
                "query": test_case['query'],
                "type": test_case['type'],
                "error": str(e),
                "response_time": time.time() - start_time
            }
            results.append(result)
    
    # Generate summary report
    generate_quality_report(results)
    
    return results

def assess_response_quality(response: str, expected_keywords: list) -> float:
    """Assess the quality of a response based on various factors."""
    score = 0.0
    
    # Check if response is not an error or "no information" message
    if "error" in response.lower() or "could not find" in response.lower():
        return 1.0
    
    # Base score for getting a response
    score += 1.0
    
    # Keyword relevance (0-2 points)
    keyword_matches = count_keyword_matches(response, expected_keywords)
    keyword_score = (keyword_matches / len(expected_keywords)) * 2.0
    score += keyword_score
    
    # Response length appropriateness (0-1 point)
    if 50 <= len(response) <= 800:  # Good length range
        score += 1.0
    elif len(response) > 30:  # At least some content
        score += 0.5
    
    # Content quality indicators (0-1 point)
    quality_indicators = [
        "based on" in response.lower(),
        "information" in response.lower(),
        not ("I don't know" in response.lower()),
        len(response.split('.')) > 1,  # Multiple sentences
        not response.count('contact') > 2  # Not just redirecting to HR
    ]
    
    quality_score = sum(quality_indicators) / len(quality_indicators)
    score += quality_score
    
    return min(score, 5.0)  # Cap at 5.0

def count_keyword_matches(response: str, keywords: list) -> int:
    """Count how many expected keywords appear in the response."""
    response_lower = response.lower()
    matches = 0
    for keyword in keywords:
        if keyword.lower() in response_lower:
            matches += 1
    return matches

def generate_quality_report(results: list):
    """Generate a summary report of the quality assessment."""
    log.info("\n" + "=" * 60)
    log.info("📊 RAG QUALITY ASSESSMENT REPORT")
    log.info("=" * 60)
    
    if not results:
        log.error("No results to analyze")
        return
    
    # Filter out error results
    valid_results = [r for r in results if 'error' not in r]
    
    if not valid_results:
        log.error("All tests failed with errors")
        return
    
    # Calculate averages
    avg_response_time = sum(r['response_time'] for r in valid_results) / len(valid_results)
    avg_quality_score = sum(r['quality_score'] for r in valid_results) / len(valid_results)
    avg_response_length = sum(r['response_length'] for r in valid_results) / len(valid_results)
    avg_keyword_matches = sum(r['keyword_matches'] for r in valid_results) / len(valid_results)
    
    log.info(f"✅ Tests completed: {len(valid_results)}/{len(results)}")
    log.info(f"⏱️  Average response time: {avg_response_time:.2f}s")
    log.info(f"🎯 Average quality score: {avg_quality_score:.2f}/5.0")
    log.info(f"📏 Average response length: {avg_response_length:.0f} characters")
    log.info(f"🔍 Average keyword matches: {avg_keyword_matches:.1f}")
    
    # Quality assessment
    if avg_quality_score >= 4.0:
        log.info("🎉 EXCELLENT: RAG system is providing high-quality answers!")
    elif avg_quality_score >= 3.0:
        log.info("✅ GOOD: RAG system is providing satisfactory answers")
    elif avg_quality_score >= 2.0:
        log.info("⚠️  FAIR: RAG system needs improvement")
    else:
        log.info("❌ POOR: RAG system requires significant optimization")
    
    # Performance assessment
    if avg_response_time <= 15:
        log.info("⚡ Performance: Fast response times")
    elif avg_response_time <= 30:
        log.info("🟡 Performance: Moderate response times")
    else:
        log.info("🔴 Performance: Slow response times")
    
    # Detailed breakdown
    log.info("\n📝 Detailed Results:")
    for i, result in enumerate(valid_results, 1):
        log.info(f"  {i}. {result['type']}: Quality {result['quality_score']:.1f}/5.0, "
                f"Time {result['response_time']:.1f}s, Keywords {result['keyword_matches']}")

if __name__ == "__main__":
    test_rag_quality()
