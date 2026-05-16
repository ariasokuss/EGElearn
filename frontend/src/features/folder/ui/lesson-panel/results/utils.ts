export function lessonProgressToText(p: number) {
    if (p < 25) return "Just started" 
    if (p < 50) return "Getting there"
    if (p < 75) return "Good progress"
    if (p < 100) return "Nearly perfect"
    return "Full mastery!" 
}