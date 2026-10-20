use rand::prelude::*;

fn main() {
    let random_number = rand::rng().random_range(1..=100);
    println!("Random number: {random_number}");
}
