#pragma once
#include <deque>
#include <vector>
#include <mutex>

// 线程安全的丢弃型队列 (Thread-Safe Dropping Queue)
// 行为模仿 Python 的 collections.deque(maxlen=N)
class SafeFrameQueue {
public:
    // 构造函数，指定最大容量
    SafeFrameQueue(size_t maxLen = 2) : m_maxLen(maxLen) {}

    // [生产者] 推入数据
    // 如果队列已满，会自动丢弃最旧的一帧 (FIFO Drop)
    void Push(const std::vector<unsigned char>& frameData) {
        std::lock_guard<std::mutex> lock(m_mtx);
        
        // 如果满了，移除头部（最旧的数据）
        if (m_queue.size() >= m_maxLen) {
            m_queue.pop_front();
        }
        
        // 新数据放入尾部
        m_queue.push_back(frameData);
    }

    // [消费者] 取出数据
    // 返回 true 表示成功取到数据，false 表示队列为空
    bool Pop(std::vector<unsigned char>& outFrame) {
        std::lock_guard<std::mutex> lock(m_mtx);
        
        if (m_queue.empty()) {
            return false;
        }

        // 取出最新的数据 (LIFO模式，如果想跟Python deque pop()一致)
        // 注意：采集通常希望取最新的一帧，所以我们取 back()
        outFrame = m_queue.back(); 
        m_queue.pop_back(); // 取出后移除
        
        // 如果你希望是严格的 FIFO (先进先出)，应该用:
        // outFrame = m_queue.front();
        // m_queue.pop_front();

        return true;
    }

    // 清空队列
    void Clear() {
        std::lock_guard<std::mutex> lock(m_mtx);
        m_queue.clear();
    }

private:
    std::deque<std::vector<unsigned char>> m_queue; // 底层容器
    size_t m_maxLen;                                // 最大容量
    std::mutex m_mtx;                               // 互斥锁
};